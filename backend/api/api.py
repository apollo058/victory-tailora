from ninja import NinjaAPI

from .models import WorkspaceLayout
from .schemas import LayoutInput, LayoutOutput


api = NinjaAPI(title="Victory Tailora API", version="0.1.0")

MODULES = [
    {
        "id": "focus",
        "name": "Focus",
        "description": "A compact view of your most important work.",
        "accent": "violet",
    },
    {
        "id": "tasks",
        "name": "Tasks",
        "description": "Keep the next actions that move your day forward.",
        "accent": "blue",
    },
    {
        "id": "calendar",
        "name": "Calendar",
        "description": "See the commitments that shape your week.",
        "accent": "orange",
    },
    {
        "id": "insights",
        "name": "Insights",
        "description": "Turn activity into lightweight progress signals.",
        "accent": "green",
    },
]


@api.get("/health")
def health(request):
    return {"status": "ok", "service": "victory-tailora-api"}


@api.get("/modules")
def modules(request):
    return MODULES


@api.get("/layouts", response=list[LayoutOutput])
def layouts(request):
    return WorkspaceLayout.objects.all()


@api.post("/layouts", response=LayoutOutput)
def create_layout(request, payload: LayoutInput):
    allowed_ids = {module["id"] for module in MODULES}
    module_ids = [module_id for module_id in payload.module_ids if module_id in allowed_ids]
    return WorkspaceLayout.objects.create(
        name=payload.name.strip() or "My workspace",
        module_ids=module_ids,
    )

