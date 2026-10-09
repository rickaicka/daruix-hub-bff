@echo off
setlocal

set "DJANGO_ADDRESS=%~1"
if "%DJANGO_ADDRESS%"=="" set "DJANGO_ADDRESS=0.0.0.0:8000"

python manage.py runserver %DJANGO_ADDRESS%
