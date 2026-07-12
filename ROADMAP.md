# ROADMAP — fueldesk

## Shipped (v0.2 AI Assist)
- AI profile free-text parse → preview → apply & regenerate
- Meal photo / caption macro estimate (confirm → check-in note)
- Equipment image/caption → chips → apply to profile
- Providers: offline heuristics, Ollama HTTP, OpenAI-compatible API
- Settings page + env overrides; masked API key; offline fallback
- Confidence badges + medical/estimate disclaimers

## Shipped (v0.1 MVP)
- Profile onboarding with diet flags + equipment
- Transparent Mifflin-St Jeor BMR/TDEE/macros
- Weekly training generator (equipment + days + experience)
- Weekly meal plan from local seed foods
- Check-ins + adjustment suggestions
- Dashboard, export JSON, modern multi-view UI
- `fueldesk serve` local desk

## Next
- [ ] CSV / barcode food import
- [ ] Progressive overload auto-progression rules
- [ ] Recipe import from Mealie
- [ ] Multi-profile household
- [x] Optional local LLM / vision assist (BYO Ollama or API key) — v0.2
- [ ] Flutter companion for pocket check-ins
- [ ] Imperial units UI toggle
- [ ] Grocery list export from weekly meals

## Non-goals
- Social network / friends feed
- Medical prescriptions or clinical dietetics
- Cloning wger / MyFitnessPal / workout.cool
