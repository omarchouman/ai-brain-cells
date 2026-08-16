from .access import brain_exists


def brain(request):
    """Things the shell needs on every page, whatever the view is doing."""
    return {"brain_exists": brain_exists()}
