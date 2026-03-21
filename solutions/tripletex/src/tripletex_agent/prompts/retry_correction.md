Step {failed_step_id} FAILED when calling the Tripletex API.

## Error from Tripletex
```
{error_detail}
```

## What was already executed successfully
{completed_steps}

## Saved variables (use as $variable_name)
{saved_vars}

## Auto-fixes applied before sending
The schema validator automatically cleaned the request body before it was sent.
These fixes were already applied — do NOT re-introduce these issues:
{auto_fixes}

## Fields removed by validator
These fields were removed because they are read-only or do not exist on the endpoint schema:
{fields_removed}

## Endpoint schema reference
The failing endpoint {failed_method} {failed_path} accepts these fields:
{endpoint_schema}

## Remaining steps from original plan
```json
{remaining_steps}
```

## Common mistakes to avoid
- Entity references in POST/PUT bodies MUST use nested object format: {{"customer": {{"id": 5}}}}, NOT flat IDs like {{"customerId": 5}}
- PUT /invoice/{{id}}/:payment uses QUERY PARAMS (paymentDate, paymentTypeId, paidAmount), NOT json_body
- PUT /invoice/{{id}}/:createCreditNote uses QUERY PARAMS (date, comment, sendToCustomer), NOT json_body
- Do not send read-only fields — they were already stripped by the validator
- Use only field names from the endpoint schema above
- If "Unresolved variables" error: a previous GET returned empty results. \
Try a broader search (e.g. GET /department?count=1&sorting=id instead of searching by name). \
Or create the missing entity first (e.g. POST /department to create it).
- save_response_fields_as format: key=your_variable_name, value=response_path. \
For lists: "values.0.id". For single objects: "value.id".

## Your task
Fix the failed step and return the corrected REMAINING steps as a JSON array.
Reference saved variables as $variable_name.
Return ONLY the JSON array, no markdown fences, no explanatory text.