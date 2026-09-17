from fastapi import Request


def get_storage(request: Request):
    return request.app.state.storage


def get_jobs(request: Request):
    return request.app.state.jobs


def get_service(request: Request):
    return request.app.state.service


def get_settings_from_app(request: Request):
    return request.app.state.settings
