{
  "description": "All Retell Custom Functions for the Sunrise receptionist. Point every tool URL at POST {{BACKEND_BASE_URL}}/webhooks/retell/tools and paste each parameters schema in the Retell dashboard.",
  "webhook_entrypoint": "{{BACKEND_BASE_URL}}/webhooks/retell/tools",
  "tools": [
    "lookup_patient.json",
    "get_clinic_catalog.json",
    "list_appointments.json",
    "search_availability.json",
    "create_appointment.json",
    "reschedule_appointment.json",
    "cancel_appointment.json",
    "create_followup.json"
  ]
}
