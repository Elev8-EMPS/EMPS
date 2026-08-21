from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Look up `key` in `dictionary` from a template, where `key` is a
    variable (e.g. a loop variable) rather than a literal - Django's
    built-in `.` lookup only supports literal keys, so this fills the
    gap. Returns '' (not None) for a missing key, since this is
    routinely dropped straight into form field values/content -
    rendering None would literally print the word 'None' into the
    field, which then gets submitted back as if it were real text."""
    if dictionary is None:
        return ""
    value = dictionary.get(key)
    return value if value is not None else ""
