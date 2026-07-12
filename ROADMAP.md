# ROADMAP — fueldesk

## Shipped (v0.3 Google ADK + modern UX)
- Optional `fueldesk[adk]` extra (`google-adk[extensions]`)
- Multi-turn AI Coach (`services/adk_coach.py`) with FunctionTools + offline fallback
- Confirm-before-apply staging for profile / meal note / equipment / protocol regen
- Gemini provider option + `GOOGLE_API_KEY` / `GEMINI_API_KEY` docs
- Mobile-first UI: bottom nav, larger touch targets, dashboard CTAs, chat-first `/ai`

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
- [x] Google ADK multi-turn coach — v0.3
- [ ] Flutter companion for pocket check-ins
- [ ] Imperial units UI toggle
- [ ] Grocery list export from weekly meals

## Non-goals
- Social network / friends feed
- Medical prescriptions or clinical dietetics
- Cloning wger / MyFitnessPal / workout.cool
