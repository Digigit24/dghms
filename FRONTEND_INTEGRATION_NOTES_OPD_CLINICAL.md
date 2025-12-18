# Frontend Integration Notes: OPD Clinical Documentation Summary


## 1. Overview of Changes

The OPD Clinical Documentation system now supports:
1.  **Multiple Doctor Support**: Multiple doctors can fill the same clinical note template on a single visit. This is tracked via a `response_sequence` number.
2.  **Canvas/Stylus Integration**: Replaced image-based canvas storage with Excalidraw JSON. Doctors can handwrite responses, and the data is stored as structured JSON.
3.  **Copy-Paste Templates**: Doctors can save and reuse common clinical note patterns.

---

## 2. Key Database Model Changes

### `ClinicalNoteTemplateResponse` (Modified)
-   **Unique Constraint**: Changed from `['visit', 'template']` to `['visit', 'template', 'response_sequence']` to allow multiple responses.
-   **New Fields**:
    -   `response_sequence`: Tracks multiple fills of the same template.
    -   `is_reviewed`, `doctor_switched_reason`, `original_assigned_doctor_id`: For review and doctor-switching workflows.
    -   `canvas_data`: For full-template canvas images.

### `ClinicalNoteTemplateFieldResponse` (Modified)
-   **Removed Fields**: `canvas_image`, `is_handwritten`.
-   **New Fields**:
    -   `full_canvas_json`: Stores Excalidraw JSON.
    -   `canvas_thumbnail`: Stores an auto-generated thumbnail of the canvas.
    -   `canvas_version_history`: Tracks changes to the canvas JSON.

### `ClinicalNoteResponseTemplate` (New Model)
-   Stores reusable copy-paste templates created by doctors. Key fields include `name`, `template_field_values` (JSON), and `usage_count`.

---

## 3. API Endpoint Summary

**All endpoints are implemented and ready for use.**

-   **/api/opd/template-responses/**: Modified to support multiple responses and canvas data.
    -   `POST`: Create a template response.
    -   `GET`: List responses (can return multiple per template).
-   **New Actions on `/api/opd/template-responses/{id}/`**:
    -   `compare/`: Compare two responses.
    -   `mark_reviewed/`: Mark a response as reviewed.
    -   `convert_to_template/`: Save a response as a reusable template.
    -   `apply_template/`: Apply a saved template to populate fields.
-   **/api/opd/template-field-responses/**: Modified to use `full_canvas_json`.
    -   `POST` / `PATCH`: Create or update a field response with `full_canvas_json` in the request body.
-   **/api/opd/response-templates/**: New endpoints for managing copy-paste templates.
    -   Standard CRUD operations (`GET`, `POST`, `PATCH`, `DELETE`).
    -   `my_templates/`: Get all templates for the current user.
    -   `clone/`: Duplicate a template.

---

## 4. Frontend Implementation Guide

### State Management (`FieldResponse` Interface)
The `FieldResponse` interface has been updated:

```typescript
interface FieldResponse {
  id: number;
  field: number;
  value_text?: string;
  full_canvas_json?: object; // NEW - Excalidraw JSON data
  canvas_thumbnail?: string; // NEW - URL to the generated thumbnail
  // ... other value fields
}
```

### API Service Layer (`FieldResponseService`)
The service for creating a field response has been updated to send JSON instead of form data for canvas input.

```typescript
class FieldResponseService {
  async createFieldResponse(
    responseId: number,
    fieldId: number,
    value: any,
    canvasJson?: object
  ): Promise<FieldResponse> {
    const payload = {
      field: fieldId,
      value_text: canvasJson ? null : value,
      full_canvas_json: canvasJson ? canvasJson : null
    };

    return await api.post(
      `/api/opd/template-responses/${responseId}/field-responses/`,
      payload
    );
  }
}
```

### UI Implementation Notes
-   **Canvas**: Use the `@excalidraw/excalidraw` library to render and edit canvas fields using the `full_canvas_json` data. The `canvas_thumbnail` URL can be used for previews.
-   **Multiple Responses**: The UI should be able to list multiple responses for a single template and provide an interface for creating new responses with a reason for the doctor switch.
-   **Copy-Paste**: Implement modals for loading, previewing, and managing reusable response templates.

---

## 5. API Request/Response Example

### Create Field Response with Canvas
**Request**:
```http
POST /api/opd/template-responses/789/field-responses/
Content-Type: application/json

{
  "field": 100,
  "full_canvas_json": {
    "type": "excalidraw",
    "version": 2,
    "elements": [
      { "type": "rectangle", "version": 1, "x": 100, "y": 100, "width": 50, "height": 50 }
    ]
  }
}
```

**Response**:
```json
{
  "id": 500,
  "field": 100,
  "full_canvas_json": { "type": "excalidraw", ... },
  "canvas_thumbnail": "/media/canvas_thumbnails/2025/12/field_500_thumb.png",
  ...
}
```
