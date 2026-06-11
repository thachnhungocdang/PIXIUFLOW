def business_profile(request):
    user = getattr(request, 'user', None)
    account_owner_name = ''
    if user and user.is_authenticated:
        account_owner_name = user.first_name.strip()

    return {
        'owner_name': account_owner_name or request.session.get('owner_name') or 'Tên chủ doanh nghiệp',
        'business_name': request.session.get('business_name') or '',
    }
