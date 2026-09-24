"""
Profile save/load - direct port of gui_main.py's _collect_profile_data and
_apply_profile_data. Operates on the MainWindow's tab references directly,
same as the original (one big class reaching into its own tree widgets).
"""
import logging


def collect_profile_data(win) -> dict:
    """Return a dict representing the current GUI state across all tabs."""
    log = logging.getLogger('DeploymentKit')
    log.debug("\n--- Saving Profile ---")

    ops = win.main_tab.selected_operations[:]
    log.debug(f"Operations order: {ops}")

    apps_state = {}
    for app in win.catalog.apps:
        if app.selected_provider is not None:
            apps_state[app.display_name] = app.selected_provider
    log.debug(f"Apps state: {apps_state}")

    tweaks_state = {}
    for tweak in win.config.tweaks.get('tweaks', []):
        action = tweak.get('selected_action')
        if action:
            tweaks_state[tweak['name']] = action
    log.debug(f"Tweaks state: {tweaks_state}")

    activators_state = win.activators_tab.get_activators_state_for_save()
    log.debug(f"Activators state: {activators_state}")

    ext_scripts = win.external_tab.get_all_scripts()
    log.debug(f"External scripts count: {len(ext_scripts)}")

    restore_selected_only = win.backup_tab.get_restore_selected_only()
    checked_sources = win.backup_tab.get_checked_sources()
    log.debug(f"Backup: restore_selected_only={restore_selected_only}, checked_sources={checked_sources}")

    return {
        'operations_order': ops,
        'apps': apps_state,
        'tweaks': tweaks_state,
        'activators': activators_state,
        'external_scripts': ext_scripts,
        'backup': {
            'restore_selected_only': restore_selected_only,
            'checked_sources': checked_sources,
        }
    }


def apply_profile_data(win, data: dict) -> dict:
    """Apply profile data to the current GUI state and refresh. Returns a
    dict of missing items per category."""
    log = logging.getLogger('DeploymentKit')
    log.debug("\n--- Loading Profile ---")
    missing = {'Apps': [], 'Tweaks': [], 'Activators': [], 'Backup Sources': []}

    # 1. Operations order
    new_ops = data.get('operations_order', [])
    valid_internal = {op['internal'] for op in win.main_tab.available_ops}
    win.main_tab.selected_operations = [op for op in new_ops if op in valid_internal]
    win.main_tab._refresh_selected_list()
    log.debug(f"Operations applied: {win.main_tab.selected_operations}")

    # 2. Apps (without reloading the catalog)
    apps_state = data.get('apps', {})
    log.debug(f"Apps from profile: {apps_state}")
    for app in win.catalog.apps:
        provider = apps_state.get(app.display_name)
        if provider is not None:
            if provider == 'offline' and (not app.is_offline_available or not app.offline_path):
                missing['Apps'].append(f"{app.display_name} (offline not available)")
                continue
            elif provider == 'winget' and not app.winget_id:
                missing['Apps'].append(f"{app.display_name} (winget ID missing)")
                continue
            elif provider == 'choco' and not app.choco_id:
                missing['Apps'].append(f"{app.display_name} (choco ID missing)")
                continue
            app.selected_provider = provider
        else:
            app.selected_provider = None
    win.apps_tab.model.refresh_all()

    # 3. Tweaks
    tweaks_state = data.get('tweaks', {})
    log.debug(f"Tweaks from profile: {tweaks_state}")
    missing['Tweaks'] = win.tweaks_tab.apply_tweaks_state(tweaks_state)

    # 4. Activators
    activators_state = data.get('activators', {})
    log.debug(f"Activators from profile: {activators_state}")
    missing['Activators'] = win.activators_tab.apply_activators_state(activators_state)

    # 5. External scripts
    ext_scripts = data.get('external_scripts', [])
    win.external_tab.apply_scripts(ext_scripts)
    log.debug(f"External scripts loaded: {len(ext_scripts)}")

    # 6. Backup settings
    backup_data = data.get('backup', {})
    log.debug(f"Backup data from profile: {backup_data}")
    if backup_data:
        if 'restore_selected_only' in backup_data:
            win.backup_tab.set_restore_selected_only(backup_data['restore_selected_only'])
        checked_sources = backup_data.get('checked_sources', [])
        win.backup_tab.apply_checked_sources(checked_sources)
        current_source_set = set(win.backup_engine.sources)
        for src in checked_sources:
            if src not in current_source_set:
                missing['Backup Sources'].append(src)

    log.debug(f"\nMissing items summary: {missing}")
    return missing
