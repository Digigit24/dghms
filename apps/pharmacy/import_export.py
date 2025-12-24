"""
Import/Export utilities for Pharmacy Products
Supports CSV, XLSX, and JSON formats
"""
import csv
import json
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any, Tuple

import pandas as pd
import openpyxl
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date

from .models import PharmacyProduct, ProductCategory


class ProductImportValidator:
    """Validates product data before import"""

    REQUIRED_FIELDS = ['product_name', 'mrp']
    OPTIONAL_FIELDS = [
        'category_id', 'company', 'batch_no', 'selling_price',
        'quantity', 'minimum_stock_level', 'expiry_date', 'is_active'
    ]

    @staticmethod
    def validate_row(row_data: Dict[str, Any], row_number: int) -> Tuple[bool, List[str]]:
        """
        Validate a single row of product data
        Returns: (is_valid, error_messages)
        """
        errors = []

        # Check required fields
        for field in ProductImportValidator.REQUIRED_FIELDS:
            if field not in row_data or not row_data[field]:
                errors.append(f"Row {row_number}: Missing required field '{field}'")

        # Validate product_name
        if 'product_name' in row_data:
            if len(str(row_data['product_name'])) > 255:
                errors.append(f"Row {row_number}: product_name too long (max 255 characters)")

        # Validate mrp
        if 'mrp' in row_data:
            try:
                mrp = Decimal(str(row_data['mrp']))
                if mrp < 0:
                    errors.append(f"Row {row_number}: MRP must be non-negative")
            except (InvalidOperation, ValueError):
                errors.append(f"Row {row_number}: Invalid MRP value")

        # Validate selling_price
        if 'selling_price' in row_data and row_data['selling_price']:
            try:
                selling_price = Decimal(str(row_data['selling_price']))
                if selling_price < 0:
                    errors.append(f"Row {row_number}: Selling price must be non-negative")

                # Check if selling price > MRP
                if 'mrp' in row_data:
                    mrp = Decimal(str(row_data['mrp']))
                    if selling_price > mrp:
                        errors.append(f"Row {row_number}: Selling price cannot exceed MRP")
            except (InvalidOperation, ValueError):
                errors.append(f"Row {row_number}: Invalid selling_price value")

        # Validate quantity
        if 'quantity' in row_data and row_data['quantity']:
            try:
                quantity = int(row_data['quantity'])
                if quantity < 0:
                    errors.append(f"Row {row_number}: Quantity must be non-negative")
            except (ValueError, TypeError):
                errors.append(f"Row {row_number}: Invalid quantity value")

        # Validate minimum_stock_level
        if 'minimum_stock_level' in row_data and row_data['minimum_stock_level']:
            try:
                min_stock = int(row_data['minimum_stock_level'])
                if min_stock < 0:
                    errors.append(f"Row {row_number}: Minimum stock level must be non-negative")
            except (ValueError, TypeError):
                errors.append(f"Row {row_number}: Invalid minimum_stock_level value")

        # Validate expiry_date
        if 'expiry_date' in row_data and row_data['expiry_date']:
            if isinstance(row_data['expiry_date'], str):
                parsed_date = parse_date(row_data['expiry_date'])
                if not parsed_date:
                    errors.append(f"Row {row_number}: Invalid expiry_date format (use YYYY-MM-DD)")

        # Validate category_id
        if 'category_id' in row_data and row_data['category_id']:
            try:
                category_id = int(row_data['category_id'])
                if not ProductCategory.objects.filter(id=category_id).exists():
                    errors.append(f"Row {row_number}: Category with ID {category_id} does not exist")
            except (ValueError, TypeError):
                errors.append(f"Row {row_number}: Invalid category_id value")

        return len(errors) == 0, errors


class ProductImporter:
    """Handles importing products from various file formats"""

    def __init__(self, tenant_id: str, skip_duplicates: bool = True):
        """
        Initialize importer
        Args:
            tenant_id: UUID of the tenant
            skip_duplicates: If True, skip products that already exist
        """
        self.tenant_id = tenant_id
        self.skip_duplicates = skip_duplicates
        self.validator = ProductImportValidator()

    def import_from_csv(self, file_content: bytes) -> Dict[str, Any]:
        """Import products from CSV file"""
        try:
            # Decode file content
            content = file_content.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(content))

            return self._process_rows(list(csv_reader))
        except Exception as e:
            return {
                'success': False,
                'error': f'CSV parsing error: {str(e)}',
                'imported': 0,
                'skipped': 0,
                'errors': []
            }

    def import_from_xlsx(self, file_content: bytes) -> Dict[str, Any]:
        """Import products from Excel file"""
        try:
            # Read Excel file using pandas
            df = pd.read_excel(io.BytesIO(file_content))

            # Convert DataFrame to list of dicts
            rows = df.to_dict('records')

            # Clean NaN values
            for row in rows:
                for key, value in row.items():
                    if pd.isna(value):
                        row[key] = None

            return self._process_rows(rows)
        except Exception as e:
            return {
                'success': False,
                'error': f'Excel parsing error: {str(e)}',
                'imported': 0,
                'skipped': 0,
                'errors': []
            }

    def import_from_json(self, file_content: bytes) -> Dict[str, Any]:
        """Import products from JSON file"""
        try:
            # Parse JSON
            data = json.loads(file_content.decode('utf-8'))

            # JSON can be array of objects or single object with array
            if isinstance(data, dict) and 'products' in data:
                rows = data['products']
            elif isinstance(data, list):
                rows = data
            else:
                return {
                    'success': False,
                    'error': 'Invalid JSON format. Expected array of products or {products: [...]}',
                    'imported': 0,
                    'skipped': 0,
                    'errors': []
                }

            return self._process_rows(rows)
        except json.JSONDecodeError as e:
            return {
                'success': False,
                'error': f'JSON parsing error: {str(e)}',
                'imported': 0,
                'skipped': 0,
                'errors': []
            }

    def _process_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process and import rows"""
        imported_count = 0
        skipped_count = 0
        all_errors = []

        for idx, row_data in enumerate(rows, start=1):
            # Validate row
            is_valid, errors = self.validator.validate_row(row_data, idx)

            if not is_valid:
                all_errors.extend(errors)
                skipped_count += 1
                continue

            # Check for duplicates
            if self.skip_duplicates:
                exists = PharmacyProduct.objects.filter(
                    tenant_id=self.tenant_id,
                    product_name__iexact=row_data['product_name'],
                    batch_no=row_data.get('batch_no')
                ).exists()

                if exists:
                    all_errors.append(f"Row {idx}: Product already exists (skipped)")
                    skipped_count += 1
                    continue

            # Create product
            try:
                self._create_product(row_data)
                imported_count += 1
            except Exception as e:
                all_errors.append(f"Row {idx}: Import error - {str(e)}")
                skipped_count += 1

        return {
            'success': len(all_errors) == 0 or imported_count > 0,
            'imported': imported_count,
            'skipped': skipped_count,
            'total_rows': len(rows),
            'errors': all_errors
        }

    def _create_product(self, row_data: Dict[str, Any]):
        """Create a product from row data"""
        # Parse expiry_date
        expiry_date = None
        if row_data.get('expiry_date'):
            if isinstance(row_data['expiry_date'], str):
                expiry_date = parse_date(row_data['expiry_date'])
            else:
                expiry_date = row_data['expiry_date']

        # Create product
        product = PharmacyProduct.objects.create(
            tenant_id=self.tenant_id,
            product_name=row_data['product_name'],
            category_id=row_data.get('category_id'),
            company=row_data.get('company', ''),
            batch_no=row_data.get('batch_no'),
            mrp=Decimal(str(row_data['mrp'])),
            selling_price=Decimal(str(row_data.get('selling_price', row_data['mrp']))),
            quantity=int(row_data.get('quantity', 0)),
            minimum_stock_level=int(row_data.get('minimum_stock_level', 10)),
            expiry_date=expiry_date,
            is_active=bool(row_data.get('is_active', True))
        )

        return product


class ProductExporter:
    """Handles exporting products to various file formats"""

    def __init__(self, queryset):
        """
        Initialize exporter
        Args:
            queryset: QuerySet of PharmacyProduct objects to export
        """
        self.queryset = queryset

    def export_to_csv(self) -> bytes:
        """Export products to CSV"""
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=self._get_export_fields(),
            extrasaction='ignore'
        )

        writer.writeheader()
        for product in self.queryset:
            writer.writerow(self._product_to_dict(product))

        return output.getvalue().encode('utf-8')

    def export_to_xlsx(self) -> bytes:
        """Export products to Excel"""
        data = [self._product_to_dict(p) for p in self.queryset]
        df = pd.DataFrame(data, columns=self._get_export_fields())

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Products')

        output.seek(0)
        return output.getvalue()

    def export_to_json(self) -> bytes:
        """Export products to JSON"""
        data = [self._product_to_dict(p) for p in self.queryset]

        json_data = {
            'products': data,
            'exported_at': datetime.now().isoformat(),
            'total_count': len(data)
        }

        return json.dumps(json_data, indent=2, default=str).encode('utf-8')

    def _get_export_fields(self) -> List[str]:
        """Get list of fields to export"""
        return [
            'id',
            'product_name',
            'category_id',
            'category_name',
            'company',
            'batch_no',
            'mrp',
            'selling_price',
            'quantity',
            'minimum_stock_level',
            'expiry_date',
            'is_active',
            'is_in_stock',
            'low_stock_warning',
            'created_at',
            'updated_at'
        ]

    def _product_to_dict(self, product: PharmacyProduct) -> Dict[str, Any]:
        """Convert product instance to dictionary"""
        return {
            'id': product.id,
            'product_name': product.product_name,
            'category_id': product.category_id,
            'category_name': product.category.name if product.category else '',
            'company': product.company or '',
            'batch_no': product.batch_no or '',
            'mrp': float(product.mrp),
            'selling_price': float(product.selling_price) if product.selling_price else float(product.mrp),
            'quantity': product.quantity,
            'minimum_stock_level': product.minimum_stock_level,
            'expiry_date': product.expiry_date.isoformat() if product.expiry_date else '',
            'is_active': product.is_active,
            'is_in_stock': product.is_in_stock,
            'low_stock_warning': product.low_stock_warning,
            'created_at': product.created_at.isoformat(),
            'updated_at': product.updated_at.isoformat()
        }
