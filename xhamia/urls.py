from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('', views.redirect_dashboard, name='home'),
    path('dashboard/', views.dashboard_antaresia, name='dashboard'),
    path('dashboard/fondi/', views.dashboard_fondi, name='dashboard_fondi'),

    # Shtepite
    path('shtepite/', views.lista_shtepive, name='lista_shtepive'),
    path('shtepite/shto/', views.shto_shtepi, name='shto_shtepi'),
    path('shtepite/<int:pk>/', views.detaje_shtepia, name='detaje_shtepia'),
    path('shtepite/<int:pk>/edito/', views.edito_shtepi, name='edito_shtepi'),
    path('shtepite/<int:pk>/fshi/', views.fshi_shtepi, name='fshi_shtepi'),

    # Pagesat Antaresia
    path('pagesat/antaresia/', views.lista_pagesa_antaresia, name='lista_pagesa_antaresia'),
    path('pagesat/antaresia/shto/', views.shto_pagese_antaresia, name='shto_pagese_antaresia'),
    path('pagesat/antaresia/<int:pk>/', views.detaje_pagesa_antaresia, name='detaje_pagesa_antaresia'),
    path('pagesat/antaresia/<int:pk>/fatura/', views.fatura_antaresia_pdf, name='fatura_antaresia_pdf'),
    path('pagesat/antaresia/<int:pk>/fshi/', views.fshi_pagese_antaresia, name='fshi_pagese_antaresia'),

    # Pagesat Fondi
    path('pagesat/fondi/', views.lista_pagesa_fondi, name='lista_pagesa_fondi'),
    path('pagesat/fondi/shto/', views.shto_pagese_fondi, name='shto_pagese_fondi'),
    path('pagesat/fondi/<int:pk>/', views.detaje_pagesa_fondi, name='detaje_pagesa_fondi'),
    path('pagesat/fondi/<int:pk>/fatura/', views.fatura_fondi_pdf, name='fatura_fondi_pdf'),
    path('pagesat/fondi/<int:pk>/fshi/', views.fshi_pagese_fondi, name='fshi_pagese_fondi'),

    # Stafi
    path('stafi/', views.lista_stafit, name='lista_stafit'),
    path('stafi/shto/', views.shto_staf, name='shto_staf'),
    path('stafi/<int:pk>/edito/', views.edito_staf, name='edito_staf'),
    path('stafi/<int:pk>/fshi/', views.fshi_staf, name='fshi_staf'),

    # Kategoritë
    path('kategoritë/', views.lista_kategorive, name='lista_kategorive'),
    path('kategoritë/shto/', views.shto_kategori, name='shto_kategori'),
    path('kategoritë/<int:pk>/edito/', views.edito_kategori, name='edito_kategori'),
]
