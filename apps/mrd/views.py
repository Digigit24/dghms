import structlog
from django.core.files.base import ContentFile
from django.http import FileResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from common.permissions import IsTenantAuthenticated
from apps.patients.models import PatientProfile
from apps.ipd.models import Admission
from apps.opd.models import Visit
from apps.clinical.models import ClinicalRecord
from apps.printing.rendering import merge_pdfs, render_pdf_from_html, render_print_html
from .models import MrdExport

log = structlog.get_logger(__name__)


class MrdBaseView(APIView):
    permission_classes = [IsTenantAuthenticated]

    def _patients(self):
        return PatientProfile.objects.filter(tenant_id=self.request.tenant_id)


class MrdWorklistView(MrdBaseView):
    def get(self, request):
        search = request.query_params.get('search', '').strip()
        qs = self._patients().order_by('-updated_at')
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(patient_id__icontains=search))
        rows = [{
            'patient_id': p.id, 'patient_name': p.full_name, 'patient_id_display': p.patient_id,
            'age': p.age, 'gender': p.gender, 'mobile': p.mobile_primary,
        } for p in qs[:100]]
        log.info('mrd_worklist_viewed', tenant_id=str(request.tenant_id), result_count=len(rows))
        return Response({'results': rows})


class MrdDossierView(MrdBaseView):
    def get(self, request, patient_id):
        patient = self._patients().filter(pk=patient_id).first()
        if not patient:
            return Response({'detail': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)
        admissions = Admission.objects.filter(tenant_id=request.tenant_id, patient_id=patient.id).order_by('-admission_date')
        visits = Visit.objects.filter(tenant_id=request.tenant_id, patient_id=patient.id).order_by('-visit_date')
        encounters, manifest = [], []
        requested_type = request.query_params.get('encounter_type')
        requested_id = request.query_params.get('encounter_id')
        for a in admissions:
            kind = 'daycare' if a.admission_type == 'daycare' else 'ipd'
            encounters.append({'id': a.id, 'type': kind, 'label': a.admission_id, 'date': a.admission_date, 'status': a.status})
            manifest.append({'id': f'admission:{a.id}', 'title': f'{kind.title()} admission - {a.admission_id}', 'category': 'Registration', 'status': 'ready', 'source_type': 'admission', 'source_id': a.id, 'encounter_id': a.id, 'encounter_type': kind, 'created_at': a.admission_date, 'required': True})
        for v in visits:
            encounters.append({'id': v.id, 'type': 'opd', 'label': getattr(v, 'visit_number', f'OPD-{v.id}'), 'date': v.visit_date, 'status': v.status})
        ipd_ids = {a.id for a in admissions}
        opd_ids = {v.id for v in visits}
        records = ClinicalRecord.objects.filter(tenant_id=request.tenant_id, status__in=['completed', 'locked'], is_active=True).select_related('form')
        for record in records:
            encounter_type = 'opd' if record.encounter_type == 'opd_visit' else ('daycare' if record.encounter_id in {a.id for a in admissions if a.admission_type == 'daycare'} else 'ipd')
            if (record.encounter_type == 'opd_visit' and record.encounter_id not in opd_ids) or (record.encounter_type == 'ipd_admission' and record.encounter_id not in ipd_ids):
                continue
            if requested_id and str(record.encounter_id) != str(requested_id):
                continue
            if requested_type and requested_type != encounter_type:
                continue
            manifest.append({'id': f'clinical:{record.id}', 'title': record.form.name, 'category': 'Filled EMR form', 'status': 'ready', 'source_type': 'clinical_record', 'source_id': record.id, 'encounter_id': record.encounter_id, 'encounter_type': encounter_type, 'created_at': record.updated_at, 'preview_url': f'/api/hms/print/preview/?form={record.form.code}&record_id={record.id}&letterhead=true&language=en', 'required': True})
        # OPD stores a DateField while IPD stores a DateTimeField; normalize
        # before sorting so a mixed longitudinal dossier is always stable.
        encounters.sort(key=lambda item: item['date'].isoformat() if item['date'] else '', reverse=True)
        total, ready = len(manifest), sum(1 for item in manifest if item['status'] == 'ready')
        log.info('mrd_dossier_viewed', tenant_id=str(request.tenant_id), patient_id=patient.id, item_count=total)
        return Response({'patient': {'patient_id': patient.id, 'patient_name': patient.full_name, 'patient_id_display': patient.patient_id, 'age': patient.age, 'gender': patient.gender, 'mobile': patient.mobile_primary}, 'encounters': encounters, 'manifest': manifest, 'completeness': {'ready': ready, 'total': total, 'missing': 0, 'percent': 100 if total else 0}})


class MrdExportView(MrdBaseView):
    def post(self, request):
        patient_id = request.data.get('patient_id')
        patient = self._patients().filter(pk=patient_id).first()
        if not patient:
            return Response({'detail': 'Patient not found.'}, status=status.HTTP_404_NOT_FOUND)
        item_ids = request.data.get('item_ids', [])
        if not isinstance(item_ids, list) or not item_ids:
            return Response({'detail': 'Select at least one completed record to generate a PDF packet.'}, status=status.HTTP_400_BAD_REQUEST)

        export = MrdExport.objects.create(tenant_id=request.tenant_id, patient_id=patient.id, requested_by_user_id=getattr(request, 'user_id', None), item_ids=item_ids, export_format='pdf')
        admission_ids = set(Admission.objects.filter(tenant_id=request.tenant_id, patient_id=patient.id).values_list('id', flat=True))
        visit_ids = set(Visit.objects.filter(tenant_id=request.tenant_id, patient_id=patient.id).values_list('id', flat=True))
        pdfs = []
        try:
            for item_id in item_ids:
                source_type, _, source_id = str(item_id).partition(':')
                if not source_id.isdigit():
                    continue
                record_id = int(source_id)
                if source_type == 'admission' and record_id in admission_ids:
                    pdfs.append(render_pdf_from_html(render_print_html('admission_form', request.tenant_id, record_id, True, 'en')))
                elif source_type == 'clinical':
                    record = ClinicalRecord.objects.filter(tenant_id=request.tenant_id, pk=record_id, status__in=['completed', 'locked'], is_active=True).select_related('form').first()
                    if record and ((record.encounter_type == 'ipd_admission' and record.encounter_id in admission_ids) or (record.encounter_type == 'opd_visit' and record.encounter_id in visit_ids)):
                        pdfs.append(render_pdf_from_html(render_print_html(record.form.code, request.tenant_id, record.id, True, 'en')))
            if not pdfs:
                export.status = MrdExport.Status.FAILED
                export.save(update_fields=['status'])
                return Response({'detail': 'None of the selected items has a completed printable record.'}, status=status.HTTP_400_BAD_REQUEST)
            export.artifact_file.save(f'mrd-packet-{export.id}.pdf', ContentFile(merge_pdfs(pdfs)), save=False)
            export.status = MrdExport.Status.COMPLETED
            export.completed_at = timezone.now()
            export.save(update_fields=['artifact_file', 'status', 'completed_at'])
        except Exception:
            export.status = MrdExport.Status.FAILED
            export.save(update_fields=['status'])
            log.exception('mrd_export_failed', tenant_id=str(request.tenant_id), patient_id=patient.id, export_id=str(export.id))
            return Response({'detail': 'The selected packet could not be rendered. Please retry or select fewer records.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        download_url = f'/api/hms/mrd/exports/{export.id}/download/'
        log.info('mrd_export_completed', tenant_id=str(request.tenant_id), patient_id=patient.id, export_id=str(export.id), item_count=len(pdfs))
        return Response({'id': str(export.id), 'status': export.status, 'progress': 100, 'download_url': download_url}, status=status.HTTP_201_CREATED)


class MrdExportDetailView(MrdBaseView):
    def get(self, request, export_id):
        export = MrdExport.objects.filter(id=export_id, tenant_id=request.tenant_id).first()
        if not export:
            return Response({'detail': 'Export not found.'}, status=status.HTTP_404_NOT_FOUND)
        payload = {'id': str(export.id), 'status': export.status, 'progress': 100 if export.status == MrdExport.Status.COMPLETED else 0}
        if export.status == MrdExport.Status.COMPLETED and export.artifact_file:
            payload['download_url'] = f'/api/hms/mrd/exports/{export.id}/download/'
        return Response(payload)


class MrdExportDownloadView(MrdBaseView):
    def get(self, request, export_id):
        export = MrdExport.objects.filter(id=export_id, tenant_id=request.tenant_id, status=MrdExport.Status.COMPLETED).first()
        if not export or not export.artifact_file:
            return Response({'detail': 'Completed export not found.'}, status=status.HTTP_404_NOT_FOUND)
        export.artifact_file.open('rb')
        return FileResponse(export.artifact_file, content_type='application/pdf', filename=f'MRD-packet-{export.patient_id}.pdf')
