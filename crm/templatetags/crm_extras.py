from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Look up `key` in `dictionary` from a template, where `key` is a
    variable (e.g. a loop variable) rather than a literal - Django's
    built-in `.` lookup only supports literal keys, so this fills the
    gap. Used on the Fee Proposal Builder's Fees tab to pre-fill saved
    amounts into the right stage/modality cell."""
    if dictionary is None:
        return None
    return dictionary.get(key)
