from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def page_url(context, param, number):
    params = context['request'].GET.copy()
    params[param] = number
    # The live endpoint is only a transport; links always target the current page.
    params.pop('mode', None)
    return '?' + params.urlencode()
