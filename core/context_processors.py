def business_profile(request):
    return {
        'owner_name': request.session.get('owner_name') or 'Tên chủ doanh nghiệp',
        'business_name': request.session.get('business_name') or '',
    }
