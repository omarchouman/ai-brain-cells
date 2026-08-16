from .access import brain_exists, brain_root


def brain(request):
    """Things the shell needs on every page, whatever the view is doing.

    The top bar renders on every page, so what it shows cannot depend on
    which view happened to pass it.
    """
    return {"brain_exists": brain_exists(), "brain_path": brain_root()}
