"""IDEA allowlist classification lists from spec 0014 section 4.4 (shared by unit and contract tests)."""

SERVED = frozenset(
    {
        "idea_status",
        "idea_open_project",
        "idea_close_project",
        "idea_list_connections",
        "idea_calculate",
        "idea_get_check_results",
        "idea_native_get_loads",
        "idea_native_set_loads",
        "idea_native_calculate",
    }
)
GAP = frozenset(
    {
        "idea_create_connection",
        "idea_set_members",
        "idea_add_plate",
        "idea_add_bolt_group",
        "idea_add_weld",
        "idea_add_cut",
        "idea_add_stiffener",
        "idea_update_operation",
        "idea_delete_operation",
        "idea_duplicate_connection",
        "idea_rename_connection",
        "idea_delete_connection",
        "idea_add_load_case",
        "idea_set_load_combinations",
        "idea_set_project_settings",
        "idea_add_material",
        "idea_add_section",
        "idea_set_loads",
        "idea_create_project",
        "idea_create_project_from_template",
    }
)
NOT_SERVED = frozenset(
    {
        "idea_save_project",
        "idea_export_iom",
        "idea_import_iom",
        "idea_export_report",
        "idea_list_templates",
        "idea_list_materials_sections",
        "idea_get_connection_stiffness",
        "idea_get_connection",
        "idea_get_model_info",
        "idea_get_project_settings",
        "idea_list_operations",
        "idea_native_info",
        "idea_native_split_pass_fail",
        "idea_native_export_template",
        "idea_native_export_iom",
        "idea_native_apply_template",
        "idea_native_apply_simple_template",
        "idea_native_delete_operations",
        "idea_native_create_from_iom",
        "idea_native_code_setup",
        "idea_native_libraries",
        "idea_native_set_design_subcode",
        "idea_native_fix_library_links",
        "idea_native_loads_from_frame_forces",
        "idea_native_create_from_joint",
        "idea_native_link",
        "idea_native_sync_from_joint",
        "idea_native_link_info",
    }
)
EXCLUDED = frozenset({"idea_run_script"})

assert len(SERVED) == 9
assert len(GAP) == 20
assert len(NOT_SERVED) == 28
assert len(EXCLUDED) == 1
assert len(SERVED | GAP | NOT_SERVED | EXCLUDED) == 58
