"""Resource location shared by source runs and installed wheels."""
from pathlib import Path


def root():
    installed = Path(__file__).resolve().parent
    if (installed/'branding/ratiolab-icon.png').is_file():
        return installed
    source = installed.parent
    if (source/'assets/branding/ratiolab-icon.png').is_file():
        return source/'assets'
    raise FileNotFoundError('RatioLab resources are missing; reinstall the application')
