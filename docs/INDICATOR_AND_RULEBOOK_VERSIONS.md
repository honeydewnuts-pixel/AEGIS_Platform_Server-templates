# Indicator stack & rulebook versioning

## Why

Screenshot trading only works if **every client chart looks the same**: same indicators, order, parameters, and colours. The brain’s CV + rule engine are calibrated to that template.

MT5 Mobile **cannot** be programmed by AEGIS to inject indicators automatically. The app therefore:

1. Downloads the **active** template from the server (`GET /api/templates/active`).
2. Shows an **install checklist** (order, params, colours).
3. Client applies it once in MT5; marks “I installed this template”.

## Current first version

| Artifact | Version | Location |
|----------|---------|----------|
| Indicator stack | **v1** | `backend/app/templates/indicator_stack_v1.json` |
| Rulebook | **v1** | `backend/app/templates/rulebook_v1.json` |
| Active pointer | | `backend/app/templates/active_profile.json` |

v1 matches the existing `colors_config.json` / `SignalRuleEngine` behaviour (`AEGIS_VISION_1.0`).

## How to add / substitute / upgrade

1. **New indicator look**  
   Copy `indicator_stack_v1.json` → `indicator_stack_v2.json`, edit colours, params, `install_order`.

2. **New trading rules**  
   Copy `rulebook_v1.json` → `rulebook_v2.json`.  
   If logic changes, implement `SignalRuleEngine` changes (or a v2 engine class) and point `engine` in the JSON.

3. **Activate** (admin key):

```http
POST /api/templates/activate
{ "indicator_stack_version": "v2", "rulebook_version": "v2" }
```

Brain hot-reloads vision config. Mobile users open **Install / Update Indicator Template** and re-apply MT5 settings.

4. **List** versions: `GET /api/templates/indicator-stacks`, `GET /api/templates/rulebooks`.

## Compatibility

Prefer activating a rulebook only with its declared `indicator_stack_version`. Mismatched stack vs rules will produce poor confidence, not a hard crash.
