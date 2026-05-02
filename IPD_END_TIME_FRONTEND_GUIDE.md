# IPD End Time (Discharge Date) - Frontend Implementation Guide

## Overview

This guide explains how to implement the frontend changes for properly handling IPD admission start time (admission_date) and end time (discharge_date) in your frontend application.

## Key Changes

### Backend Changes
The backend now supports:
1. **Admission Date**: Stored as DateTimeField with both date AND time
2. **Discharge Date**: Stored as DateTimeField with both date AND time
3. **Validation**: Ensures discharge_date is after admission_date
4. **Flexible Discharge**: Supports setting a custom discharge_date instead of always using current time

---

## Implementation Guide

### 1. Create IPD Admission (with optional end time)

#### API Endpoint
```
POST /api/ipd/admissions/
```

#### Request Payload
```json
{
  "patient": 5,
  "doctor_id": "550e8400-e29b-41d4-a716-446655440000",
  "ward": 2,
  "bed": 8,
  "admission_date": "2026-05-02T14:30:00Z",
  "reason": "Post-operative care",
  "provisional_diagnosis": "Appendicitis - Post-op",
  "discharge_date": "2026-05-05T10:00:00Z"
}
```

#### Important Fields
- **admission_date**: ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
  - Required: Yes, defaults to current time
  - Type: DateTime
  - Description: When patient is admitted WITH time

- **discharge_date**: ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
  - Required: No (optional)
  - Type: DateTime (can include time)
  - Description: When patient will be discharged WITH time
  - Validation: Must be >= admission_date

#### Frontend Implementation Example (React)

```javascript
const AdmissionForm = () => {
  const [formData, setFormData] = useState({
    patient: '',
    doctor_id: '',
    ward: '',
    bed: '',
    admission_date: new Date().toISOString(),
    reason: '',
    provisional_diagnosis: '',
    discharge_date: '' // Optional
  });

  const handleDateTimeChange = (field, value) => {
    // Ensure ISO 8601 format with time
    const isoString = new Date(value).toISOString();
    setFormData(prev => ({
      ...prev,
      [field]: isoString
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    // Validate discharge_date >= admission_date
    if (formData.discharge_date) {
      const admissionTime = new Date(formData.admission_date);
      const dischargeTime = new Date(formData.discharge_date);
      
      if (dischargeTime < admissionTime) {
        alert('Discharge date must be after admission date');
        return;
      }
    }

    try {
      const response = await fetch('/api/ipd/admissions/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(formData)
      });

      if (response.ok) {
        const admission = await response.json();
        console.log('Admission created:', admission);
        // Store admission with admission_date and discharge_date
      } else {
        const errors = await response.json();
        console.error('Validation errors:', errors);
        // discharge_date error example:
        // {"discharge_date": ["Discharge date must be after or equal to admission date"]}
      }
    } catch (error) {
      console.error('Error:', error);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* Admission Date with Time Picker */}
      <label>
        Admission Date & Time:
        <input
          type="datetime-local"
          value={new Date(formData.admission_date).toISOString().slice(0, 16)}
          onChange={(e) => handleDateTimeChange('admission_date', e.target.value)}
          required
        />
      </label>

      {/* Discharge Date with Time Picker (Optional) */}
      <label>
        Expected Discharge Date & Time (Optional):
        <input
          type="datetime-local"
          value={formData.discharge_date ? 
            new Date(formData.discharge_date).toISOString().slice(0, 16) : ''
          }
          onChange={(e) => handleDateTimeChange('discharge_date', e.target.value)}
        />
      </label>

      {/* Other fields... */}
      <button type="submit">Create Admission</button>
    </form>
  );
};
```

---

### 2. Display Admission Details

#### API Response
```json
{
  "id": 10,
  "admission_id": "IPD/20260502/001",
  "patient": 5,
  "patient_name": "John Doe",
  "doctor_id": "550e8400-e29b-41d4-a716-446655440000",
  "ward": 2,
  "ward_name": "General Ward",
  "bed": 8,
  "bed_number": "A-101",
  "admission_date": "2026-05-02T14:30:00Z",
  "reason": "Post-operative care",
  "provisional_diagnosis": "Appendicitis - Post-op",
  "final_diagnosis": "",
  "discharge_date": null,
  "discharge_summary": "",
  "discharge_type": "",
  "status": "admitted",
  "length_of_stay": 0,
  "created_by_user_id": "user-uuid",
  "discharged_by_user_id": null,
  "created_at": "2026-05-02T14:30:00Z",
  "updated_at": "2026-05-02T14:30:00Z"
}
```

#### Frontend Display Example

```javascript
const AdmissionDetails = ({ admission }) => {
  // Format dates with time
  const formatDateTime = (dateString) => {
    return new Date(dateString).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  return (
    <div className="admission-card">
      <h2>{admission.admission_id}</h2>
      <p><strong>Patient:</strong> {admission.patient_name}</p>
      <p><strong>Ward:</strong> {admission.ward_name}</p>
      <p><strong>Bed:</strong> {admission.bed_number}</p>
      
      {/* Display with time */}
      <p>
        <strong>Admitted:</strong> {formatDateTime(admission.admission_date)}
      </p>
      
      {admission.discharge_date ? (
        <p>
          <strong>Discharged:</strong> {formatDateTime(admission.discharge_date)}
        </p>
      ) : (
        <p><strong>Status:</strong> {admission.status}</p>
      )}

      <p><strong>Length of Stay:</strong> {admission.length_of_stay} days</p>
    </div>
  );
};
```

---

### 3. Discharge Patient (with optional end time)

#### API Endpoint
```
POST /api/ipd/admissions/{admission_id}/discharge/
```

#### Request Payload - Option A: Default to Current Time
```json
{
  "discharge_type": "Normal",
  "discharge_summary": "Patient recovered well. Continue medications as prescribed."
}
```

#### Request Payload - Option B: Specify Exact Discharge Time
```json
{
  "discharge_date": "2026-05-05T10:30:00Z",
  "discharge_type": "Normal",
  "discharge_summary": "Patient recovered well. Continue medications as prescribed."
}
```

#### Response
```json
{
  "id": 10,
  "admission_id": "IPD/20260502/001",
  "patient": 5,
  "patient_name": "John Doe",
  "admission_date": "2026-05-02T14:30:00Z",
  "discharge_date": "2026-05-05T10:30:00Z",
  "discharge_type": "Normal",
  "discharge_summary": "Patient recovered well...",
  "status": "discharged",
  "length_of_stay": 2,
  "created_at": "2026-05-02T14:30:00Z",
  "updated_at": "2026-05-05T10:30:00Z"
}
```

#### Frontend Implementation Example

```javascript
const DischargeForm = ({ admissionId }) => {
  const [formData, setFormData] = useState({
    discharge_type: 'Normal',
    discharge_summary: '',
    discharge_date: '' // Optional specific time
  });
  const [useCurrentTime, setUseCurrentTime] = useState(true);

  const handleDischarge = async (e) => {
    e.preventDefault();

    const payload = {
      discharge_type: formData.discharge_type,
      discharge_summary: formData.discharge_summary
    };

    // Only include discharge_date if custom time is selected
    if (!useCurrentTime && formData.discharge_date) {
      payload.discharge_date = new Date(formData.discharge_date).toISOString();
    }

    try {
      const response = await fetch(`/api/ipd/admissions/${admissionId}/discharge/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        const updated = await response.json();
        console.log('Patient discharged:', updated);
        console.log(`Discharge Date: ${updated.discharge_date}`);
        console.log(`Length of Stay: ${updated.length_of_stay} days`);
        // Navigate or refresh
      } else {
        const errors = await response.json();
        console.error('Error:', errors);
        // Error example:
        // {"error": "Discharge date must be after or equal to admission date"}
      }
    } catch (error) {
      console.error('Error:', error);
    }
  };

  return (
    <form onSubmit={handleDischarge}>
      <div>
        <label>
          <input
            type="radio"
            checked={useCurrentTime}
            onChange={() => setUseCurrentTime(true)}
          />
          Discharge Now (Current Time)
        </label>
      </div>

      <div>
        <label>
          <input
            type="radio"
            checked={!useCurrentTime}
            onChange={() => setUseCurrentTime(false)}
          />
          Specific Discharge Date & Time
        </label>

        {!useCurrentTime && (
          <input
            type="datetime-local"
            value={formData.discharge_date ? 
              new Date(formData.discharge_date).toISOString().slice(0, 16) : ''
            }
            onChange={(e) => setFormData(prev => ({
              ...prev,
              discharge_date: e.target.value
            }))}
            required
          />
        )}
      </div>

      <label>
        Discharge Type:
        <select
          value={formData.discharge_type}
          onChange={(e) => setFormData(prev => ({
            ...prev,
            discharge_type: e.target.value
          }))}
        >
          <option>Normal</option>
          <option>Against Medical Advice</option>
          <option>Referred</option>
          <option>Death</option>
        </select>
      </label>

      <label>
        Discharge Summary:
        <textarea
          value={formData.discharge_summary}
          onChange={(e) => setFormData(prev => ({
            ...prev,
            discharge_summary: e.target.value
          }))}
          placeholder="Patient instructions, medications, follow-up care..."
        />
      </label>

      <button type="submit">Discharge Patient</button>
    </form>
  );
};
```

---

### 4. List Admissions with Date/Time Display

#### API Endpoint
```
GET /api/ipd/admissions/
```

#### Query Parameters
```
?status=admitted       # Filter by status
?ward=2               # Filter by ward
?date_from=2026-05-01 # Filter by date range
&date_to=2026-05-31
```

#### Frontend Component Example

```javascript
const AdmissionsList = () => {
  const [admissions, setAdmissions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAdmissions();
  }, []);

  const fetchAdmissions = async () => {
    try {
      const response = await fetch('/api/ipd/admissions/', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      setAdmissions(data.results);
    } catch (error) {
      console.error('Error fetching admissions:', error);
    } finally {
      setLoading(false);
    }
  };

  const calculateLOS = (admission) => {
    const start = new Date(admission.admission_date);
    const end = admission.discharge_date ? 
      new Date(admission.discharge_date) : 
      new Date();
    const days = Math.ceil((end - start) / (1000 * 60 * 60 * 24));
    return days;
  };

  if (loading) return <p>Loading...</p>;

  return (
    <table>
      <thead>
        <tr>
          <th>Admission ID</th>
          <th>Patient</th>
          <th>Admitted (Date & Time)</th>
          <th>Discharged (Date & Time)</th>
          <th>LOS (Days)</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {admissions.map(admission => (
          <tr key={admission.id}>
            <td>{admission.admission_id}</td>
            <td>{admission.patient_name}</td>
            <td>
              {new Date(admission.admission_date).toLocaleString()}
            </td>
            <td>
              {admission.discharge_date 
                ? new Date(admission.discharge_date).toLocaleString()
                : '-'
              }
            </td>
            <td>{calculateLOS(admission)}</td>
            <td>
              <span className={`status-badge status-${admission.status}`}>
                {admission.status}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
```

---

## Key Implementation Points

### 1. DateTime Formatting
Always display both date AND time:
```javascript
// ❌ Wrong - Only shows date
new Date(dateString).toLocaleDateString()

// ✅ Correct - Shows date and time
new Date(dateString).toLocaleString()

// ✅ Custom format
new Date(dateString).toLocaleString('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  timeZone: 'UTC'
})
```

### 2. Input Type for DateTime
```html
<!-- ✅ Correct - Captures both date and time -->
<input type="datetime-local" />

<!-- ❌ Wrong - Only captures date -->
<input type="date" />
```

### 3. ISO 8601 Format
Always use ISO 8601 format for API communication:
```javascript
// ✅ Correct
new Date().toISOString() // "2026-05-02T14:30:00.000Z"

// ✅ Correct for datetime-local input
new Date().toISOString().slice(0, 16) // "2026-05-02T14:30"

// ❌ Wrong - Not ISO format
"05-02-2026 14:30"
```

### 4. Validation
```javascript
// Always validate discharge_date >= admission_date
const isValidDischarge = (admissionDate, dischargeDate) => {
  if (!dischargeDate) return true; // Optional field
  return new Date(dischargeDate) >= new Date(admissionDate);
};
```

### 5. Error Handling
```javascript
// Backend may return validation errors
if (!response.ok) {
  const errors = await response.json();
  // Example error response:
  // {
  //   "discharge_date": [
  //     "Discharge date must be after or equal to admission date"
  //   ]
  // }
  handleValidationErrors(errors);
}
```

---

## API Error Responses

### Invalid Discharge Date
```json
{
  "error": "Discharge date must be after or equal to admission date"
}
```

### Invalid Date Format
```json
{
  "error": "Invalid discharge_date format. Use ISO 8601 format."
}
```

### Patient Not Admitted
```json
{
  "error": "Patient is not currently admitted"
}
```

---

## Best Practices

1. **Always Use DateTime Fields**: Never use date-only fields for admission/discharge
2. **Client-side Validation**: Validate before sending to server
3. **Show Time in Display**: Always show both date and time in lists and details
4. **Calculate LOS Properly**: Use actual discharge_date or current time if not discharged
5. **Handle Timezones**: Use UTC or local timezone consistently
6. **Confirm Before Discharge**: Show confirmation modal with final details
7. **Prevent Backdating**: Consider restricting discharge dates in the past (optional)

---

## Summary

The IPD end time feature properly stores and validates:
- **Admission Date/Time**: Captured when patient is admitted
- **Discharge Date/Time**: Captured when patient is discharged
- **Validation**: Ensures discharge is after admission
- **Flexibility**: Supports both current-time discharge and specific date/time

Implement the frontend forms with `datetime-local` inputs and always display both date and time in your UI components.
