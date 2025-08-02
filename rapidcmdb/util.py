import os
from importlib import resources
from pathlib import Path


def get_db_path():
    """Get the path to the tfsm_templates.db file."""
    # First try direct file access (development mode)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    direct_path = os.path.join(current_dir, 'tfsm_templates.db')
    if os.path.exists(direct_path):
        return direct_path

    # If not found, try package resources (installed package mode)
    try:
        with resources.files('secure_cartography').joinpath('tfsm_templates.db') as db_path:
            return str(db_path)
    except Exception as e:
        raise FileNotFoundError(f"Could not find tfsm_templates.db: {str(e)}")