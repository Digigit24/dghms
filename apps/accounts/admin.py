# =============================================================================
# DEPRECATED - DO NOT USE
# =============================================================================
# This file is deprecated and should NOT be used.
#
# Reason: DigiHMS no longer uses Django's built-in User model.
# Authentication is now handled via SuperAdmin with JWT tokens.
#
# User references have been replaced with user_id (UUID) fields.
# DoctorProfile and PatientProfile are now standalone models without
# ForeignKey relationships to User.
#
# For user management, use the SuperAdmin system.
# For profile management, use the respective model admins:
#   - apps/doctors/admin.py for DoctorProfile
#   - apps/patients/admin.py for PatientProfile
# =============================================================================

# from django.contrib import admin
# from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
# from django.contrib.auth import get_user_model
# from django.utils.html import format_html
# from common.admin_site import hms_admin_site

# User = get_user_model()

# This entire file has been commented out as it's no longer applicable
# to the SuperAdmin integration architecture.
