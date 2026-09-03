from core.config import load_config
from core.planner import build_initial_plan
from core.deployment import build_deployment_manifest
from core.lifecycle import (
    start_service,
    stop_service,
)
from adapters.executor import get_executor


CONTROL_PLANE_ROLES = {
    "platform_api",
}


def build_control_context():
    """
    Build the objects required to control the deployment.

    This keeps Platform API actions out of the HTTP layer.
    Future CLI/Admin UI integrations should reuse this control layer.
    """

    config = load_config()
    plan = build_initial_plan()

    manifest = build_deployment_manifest(
        plan,
        config,
    )

    executor_name = config["runtime"]["executor"]

    if executor_name != "process":
        raise RuntimeError(
            "Real lifecycle control is currently "
            "implemented for process execution only."
        )

    executor = get_executor(
        executor_name
    )

    return {
        "config": config,
        "plan": plan,
        "manifest": manifest,
        "executor": executor,
    }


def get_workload_services(manifest):
    """
    Return enabled services belonging to the AI workload.

    PROVISIONAL:
    platform_api is currently the only control-plane service.

    Future service metadata should explicitly classify services
    by control/data/management plane.
    """

    return [
        service
        for service in manifest["services"]
        if (
            service["enabled"]
            and service["role"]
            not in CONTROL_PLANE_ROLES
        )
    ]


def restart_workload():
    """
    Restart the managed AI workload while preserving the
    Platform API process handling this request.

    PROVISIONAL:
    This operation is synchronous. A future Admin UI should
    use asynchronous operations/jobs with progress reporting.
    """

    context = build_control_context()

    manifest = context["manifest"]
    executor = context["executor"]

    services = get_workload_services(
        manifest
    )

    results = []

    # Stop dependent services first.
    for service in reversed(services):
        result = stop_service(
            service["id"],
            service["spec"],
        )

        results.append({
            "service_id": service["id"],
            "action": "stop",
            "status": result["status"],
        })

        if result["status"] == "failed":
            return {
                "ok": False,
                "action": "restart",
                "control_plane_preserved": True,
                "results": results,
            }

    # Start dependency order.
    for service in services:
        timeout = (
            240
            if service["role"] == "inference"
            else 180
        )

        result = start_service(
            service["id"],
            service["spec"],
            executor,
            timeout=timeout,
        )

        results.append({
            "service_id": service["id"],
            "action": "start",
            "status": result["status"],
        })

        if result["status"] == "failed":
            return {
                "ok": False,
                "action": "restart",
                "control_plane_preserved": True,
                "results": results,
            }

    return {
        "ok": True,
        "action": "restart",
        "control_plane_preserved": True,
        "results": results,
    }


def _invalidate_capacity_evidence_after_storage_mutation(
    reason,
):
    """
    Invalidate reusable empirical capacity evidence after a
    SUCCESSFUL platform-managed storage mutation.

    This boundary deliberately lives in core.control rather than
    HTTP/API code or individual provider adapters.

    The cache invalidator also advances the logical platform-storage
    generation, so old capacity evidence becomes stale even if total
    used bytes later happen to return to the same numerical value.
    """

    from core.storage_capacity_cache import (
        invalidate_capacity_cache,
    )

    return invalidate_capacity_cache(
        reason
    )


def download_inventory_model(
    *,
    provider,
    source_model_id,
    revision="main",
    target_name=None,
):
    """
    Control-plane action for obtaining a model artifact.

    Hugging Face storage-safety sequence:

        acquire shared storage-operation lock
            ->
        resolve requested revision to immutable repository revision
            ->
        resolve complete repository manifest
            ->
        calculate high-confidence peak additional storage
            ->
        rebuild CURRENT storage plan
            ->
        commit-time storage admission
            ->
        operation-sized verification
            ->
        download the SAME immutable revision
            ->
        successful mutation invalidates capacity evidence
            ->
        release lock

    PROVISIONAL:
    Non-Hugging-Face providers retain their previous control path
    during this incremental integration step.

    Downloads remain synchronous for the current exoskeleton.
    Future Admin UI operations should use asynchronous jobs.
    """

    from core.model_transfer import (
        download_model,
    )


    #
    # Incremental integration boundary:
    #
    # Step 30 secures Hugging Face remote downloads only.
    # Existing providers retain legacy behavior until their explicit
    # storage-safety boundary is implemented.
    #

    #
    # Local-file transfers MUST reuse the already serialized,
    # high-confidence import path.
    #
    # This closes the generic-download bypass that previously let
    # provider="local_files" call ModelTransfer directly.
    #

    if provider == "local_files":

        resolved_target_name = (
            target_name
            if target_name is not None
            else (
                provider
                + "-"
                + source_model_id
            )
        )


        routed = (
            import_inventory_model(
                source_path=(
                    source_model_id
                ),

                target_name=(
                    resolved_target_name
                ),
            )
        )


        if routed.get(
            "ok",
            False,
        ):
            return {
                "ok": True,

                "action": (
                    "download_model"
                ),

                "result": (
                    routed.get(
                        "result"
                    )
                ),

                "storage_admission": (
                    routed.get(
                        "storage_admission"
                    )
                ),

                "routed_via": (
                    "import_inventory_model"
                ),
            }


        return {
            "ok": False,

            "action": (
                "download_model"
            ),

            "error": (
                routed.get(
                    "error"
                )
            ),

            "storage_admission": (
                routed.get(
                    "storage_admission"
                )
            ),

            "routed_via": (
                "import_inventory_model"
            ),
        }


    #
    # Fail closed for every provider whose storage mutation
    # semantics have not explicitly been integrated.
    #
    # This is important for future ModelTransfer adapters:
    # merely adding a provider to config must never silently create
    # an unsafe mutation path.
    #

    if provider != "huggingface":

        from core.config import (
            load_config,
        )


        config = load_config()

        transfer_config = config.get(
            "model_transfer",
            {},
        )


        if not transfer_config.get(
            "enabled",
            False,
        ):
            return {
                "ok": False,

                "action": (
                    "download_model"
                ),

                "error": {
                    "code": (
                        "transfer_failed"
                    ),

                    "detail": (
                        "Model transfer is disabled."
                    ),
                },
            }


        if provider not in transfer_config.get(
            "providers",
            [],
        ):
            return {
                "ok": False,

                "action": (
                    "download_model"
                ),

                "error": {
                    "code": (
                        "provider_not_enabled"
                    ),

                    "detail": (
                        "ModelTransfer provider "
                        + repr(
                            provider
                        )
                        + " is not enabled."
                    ),
                },
            }


        return {
            "ok": False,

            "action": (
                "download_model"
            ),

            "error": {
                "code": (
                    "storage_safety_not_implemented"
                ),

                "detail": (
                    "ModelTransfer provider "
                    + repr(
                        provider
                    )
                    + " is enabled but does not yet have "
                    "an explicit storage commit-safety "
                    "integration."
                ),
            },
        }


    #
    # Hugging Face safe-commit path.
    #

    from core.config import (
        load_config,
    )

    from core.model_remote_storage_preflight import (
        build_huggingface_storage_candidate,
    )

    from core.model_storage_requirements import (
        estimate_model_install_storage,
    )

    from core.storage_commit_admission import (
        evaluate_storage_commit_admission,
    )

    from core.storage_operation_lock import (
        StorageOperationBusyError,
        storage_operation_lock,
    )

    from core.storage_planning import (
        build_storage_plan,
        build_storage_plan_for_commit,
    )


    config = load_config()

    transfer_config = config.get(
        "model_transfer",
        {},
    )


    #
    # Preserve provider configuration semantics before making a
    # remote manifest request.
    #

    if not transfer_config.get(
        "enabled",
        False,
    ):
        return {
            "ok": False,

            "action": (
                "download_model"
            ),

            "error": {
                "code": (
                    "transfer_failed"
                ),

                "detail": (
                    "Model transfer is disabled."
                ),
            },
        }


    if provider not in transfer_config.get(
        "providers",
        [],
    ):
        return {
            "ok": False,

            "action": (
                "download_model"
            ),

            "error": {
                "code": (
                    "provider_not_enabled"
                ),

                "detail": (
                    "ModelTransfer provider "
                    + repr(
                        provider
                    )
                    + " is not enabled."
                ),
            },
        }


    settings = config.get(
        "storage_capacity",
        {},
    )


    overhead_fraction = float(
        settings.get(
            "model_operation_overhead_fraction",
            0.10,
        )
    )


    overhead_min_bytes = int(
        float(
            settings.get(
                "model_operation_overhead_min_gb",
                1.0,
            )
        )
        * (
            1024 ** 3
        )
    )


    try:
        with storage_operation_lock(
            "model_download_huggingface",

            config=config,
        ):

            #
            # Resolve branch/tag -> immutable revision and complete
            # file manifest INSIDE the mutation lock.
            #

            try:
                candidate = (
                    build_huggingface_storage_candidate(
                        source_model_id,

                        revision=revision,
                    )
                )

            except RuntimeError as exc:
                return {
                    "ok": False,

                    "action": (
                        "download_model"
                    ),

                    "error": {
                        "code": (
                            "storage_preflight_failed"
                        ),

                        "detail": str(
                            exc
                        ),
                    },
                }


            manifest = (
                candidate.get(
                    "remote_manifest"
                )
                or {}
            )


            if not manifest.get(
                "resolved",
                False,
            ):
                return {
                    "ok": False,

                    "action": (
                        "download_model"
                    ),

                    "error": {
                        "code": (
                            "storage_preflight_failed"
                        ),

                        "detail": (
                            "Hugging Face repository manifest "
                            "could not be resolved completely."
                        ),

                        "reason": (
                            manifest.get(
                                "exactness"
                            )
                        ),
                    },

                    "remote_manifest": (
                        manifest
                    ),
                }


            immutable_revision = (
                candidate[
                    "source"
                ][
                    "revision"
                ]
            )


            requirement = (
                estimate_model_install_storage(
                    candidate,

                    overhead_fraction=(
                        overhead_fraction
                    ),

                    overhead_min_bytes=(
                        overhead_min_bytes
                    ),
                )
            )


            storage_plan = (
                build_storage_plan(
                    config=config,

                    calibrate_if_required=False,
                )
            )


            #
            # A host whose capacity has never been characterized
            # resolves no storage budget, and admission then denies
            # every download. Prove what THIS download needs, inside
            # the lock already held, or leave the denial untouched.
            #

            storage_plan = (
                build_storage_plan_for_commit(
                    requirement,

                    config=config,

                    storage_plan=(
                        storage_plan
                    ),
                )
            )


            admission = (
                evaluate_storage_commit_admission(
                    requirement,

                    config=config,

                    storage_plan=(
                        storage_plan
                    ),
                )
            )


            if not admission.get(
                "allowed",
                False,
            ):
                return {
                    "ok": False,

                    "action": (
                        "download_model"
                    ),

                    "error": {
                        "code": (
                            "storage_admission_denied"
                        ),

                        "detail": (
                            "Hugging Face model download was "
                            "denied by commit-time storage "
                            "admission."
                        ),

                        "reason": (
                            admission.get(
                                "reason"
                            )
                        ),
                    },

                    "storage_admission": (
                        admission
                    ),

                    "remote_manifest": (
                        manifest
                    ),
                }


            #
            # TOCTOU protection:
            #
            # The transfer receives the immutable revision resolved
            # by the SAME manifest used for commit sizing.
            #
            # A moving branch such as "main" therefore cannot change
            # between manifest inspection and transfer.
            #

            try:
                result = download_model(
                    provider=provider,

                    source_model_id=(
                        source_model_id
                    ),

                    revision=(
                        immutable_revision
                    ),

                    target_name=(
                        target_name
                    ),
                )

            except RuntimeError as exc:

                detail = str(
                    exc
                )


                if detail.startswith(
                    "Destination already exists:"
                ):
                    code = (
                        "already_exists"
                    )

                elif "not enabled" in detail:
                    code = (
                        "provider_not_enabled"
                    )

                else:
                    code = (
                        "transfer_failed"
                    )


                return {
                    "ok": False,

                    "action": (
                        "download_model"
                    ),

                    "error": {
                        "code": code,
                        "detail": detail,
                    },

                    "storage_admission": (
                        admission
                    ),

                    "remote_manifest": (
                        manifest
                    ),
                }


            #
            # Preserve the user's requested revision in the response
            # while also exposing the immutable preflight revision.
            #
            # Persistent Inventory still receives the actual resolved
            # revision from the transfer worker.
            #

            source_result = (
                result.get(
                    "source"
                )
                if isinstance(
                    result,
                    dict,
                )
                else None
            )


            if isinstance(
                source_result,
                dict,
            ):
                source_result[
                    "requested_revision"
                ] = revision

                source_result[
                    "preflight_resolved_revision"
                ] = (
                    immutable_revision
                )


            _invalidate_capacity_evidence_after_storage_mutation(
                "model_download_succeeded"
            )


            return {
                "ok": True,

                "action": (
                    "download_model"
                ),

                "result": result,

                "storage_admission": (
                    admission
                ),

                "remote_manifest": (
                    manifest
                ),
            }


    except StorageOperationBusyError as exc:

        return {
            "ok": False,

            "action": (
                "download_model"
            ),

            "error": {
                "code": (
                    "storage_operation_busy"
                ),

                "detail": str(
                    exc
                ),
            },
        }




def import_inventory_model(
    *,
    source_path,
    target_name,
):
    """
    Import a local model directory into managed Inventory.

    The original directory remains untouched.

    Storage-safety sequence:

        acquire shared storage-operation lock
            ->
        measure local source before copying
            ->
        rebuild CURRENT storage plan
            ->
        commit-time storage admission
            ->
        final operation-sized verification
            ->
        perform copy while the lock remains held
            ->
        successful mutation invalidates capacity evidence
            ->
        release lock

    Failed or denied operations do not advance storage generation.
    """

    from core.config import (
        load_config,
    )

    from core.model_storage_requirements import (
        estimate_local_import_storage,
    )

    from core.model_transfer import (
        download_model,
    )

    from core.storage_commit_admission import (
        evaluate_storage_commit_admission,
    )

    from core.storage_operation_lock import (
        StorageOperationBusyError,
        storage_operation_lock,
    )

    from core.storage_planning import (
        build_storage_plan,
    )


    config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )


    overhead_fraction = float(
        settings.get(
            "model_operation_overhead_fraction",
            0.10,
        )
    )


    overhead_min_bytes = int(
        float(
            settings.get(
                "model_operation_overhead_min_gb",
                1.0,
            )
        )
        * (
            1024 ** 3
        )
    )


    try:
        with storage_operation_lock(
            "model_import",
            config=config,
        ):

            #
            # Requirement is calculated INSIDE the lock so another
            # platform-managed mutation cannot race between sizing,
            # planning, verification, and execution.
            #

            requirement = (
                estimate_local_import_storage(
                    source_path,

                    overhead_fraction=(
                        overhead_fraction
                    ),

                    overhead_min_bytes=(
                        overhead_min_bytes
                    ),
                )
            )


            #
            # Rebuild current state only after acquiring the shared
            # mutation lock.
            #

            storage_plan = (
                build_storage_plan(
                    config=config,

                    calibrate_if_required=False,
                )
            )


            admission = (
                evaluate_storage_commit_admission(
                    requirement,

                    config=config,

                    storage_plan=(
                        storage_plan
                    ),
                )
            )


            if not admission.get(
                "allowed",
                False,
            ):
                return {
                    "ok": False,

                    "action": (
                        "import_model"
                    ),

                    "error": {
                        "code": (
                            "storage_admission_denied"
                        ),

                        "detail": (
                            "Local model import was denied "
                            "by commit-time storage admission."
                        ),

                        "reason": (
                            admission.get(
                                "reason"
                            )
                        ),
                    },

                    "storage_admission": (
                        admission
                    ),
                }


            #
            # The lock remains held during the actual copy.
            #

            try:
                result = download_model(
                    provider="local_files",

                    source_model_id=(
                        source_path
                    ),

                    revision=None,

                    target_name=(
                        target_name
                    ),
                )

            except RuntimeError as exc:
                detail = str(
                    exc
                )

                if detail.startswith(
                    "Destination already exists:"
                ):
                    code = (
                        "already_exists"
                    )

                else:
                    code = (
                        "import_failed"
                    )

                return {
                    "ok": False,

                    "action": (
                        "import_model"
                    ),

                    "error": {
                        "code": code,
                        "detail": detail,
                    },

                    "storage_admission": (
                        admission
                    ),
                }


            #
            # Only a successful storage mutation changes capacity
            # generation / invalidates cached empirical evidence.
            #

            _invalidate_capacity_evidence_after_storage_mutation(
                "model_import_succeeded"
            )


            return {
                "ok": True,

                "action": (
                    "import_model"
                ),

                "result": result,

                "storage_admission": (
                    admission
                ),
            }


    except StorageOperationBusyError as exc:
        return {
            "ok": False,

            "action": (
                "import_model"
            ),

            "error": {
                "code": (
                    "storage_operation_busy"
                ),

                "detail": str(
                    exc
                ),
            },
        }




def delete_inventory_model(
    *,
    model_id,
):
    """
    Delete one platform-managed model through the shared storage
    mutation boundary.

    Delete does not require positive-capacity admission because it
    releases platform storage rather than consuming additional
    storage.

    Safety sequence:

        acquire shared storage-operation lock
            ->
        execute existing delete safety checks + mutation
            ->
        successful mutation invalidates capacity evidence
            ->
        release lock

    Failed deletes do not advance storage generation.
    """

    from core.model_delete import (
        delete_model,
    )

    from core.storage_operation_lock import (
        StorageOperationBusyError,
        storage_operation_lock,
    )


    try:
        with storage_operation_lock(
            "model_delete",
        ):

            result = (
                delete_model(
                    model_id
                )
            )


            if result.get(
                "ok",
                False,
            ):
                _invalidate_capacity_evidence_after_storage_mutation(
                    "model_delete_succeeded"
                )


            return result


    except StorageOperationBusyError as exc:
        return {
            "ok": False,

            "error": {
                "code": (
                    "storage_operation_busy"
                ),

                "detail": str(
                    exc
                ),
            },
        }




def update_inventory_model(
    *,
    model_id,
    revision="main",
):
    """
    Control-plane action for safely updating a managed model.

    Hugging Face update storage-safety sequence:

        acquire shared storage-operation lock
            ->
        inspect current Inventory state
            ->
        preserve existing early update safety checks
            ->
        resolve requested revision to immutable repository revision
            ->
        resolve complete replacement manifest
            ->
        calculate high-confidence peak ADDITIONAL storage
            ->
        rebuild current storage plan
            ->
        commit-time storage admission
            ->
        operation-sized point-in-time verification
            ->
        call rollback-safe update using SAME immutable revision
            ->
        success invalidates capacity evidence
            ->
        release lock

    The existing model artifact is already counted in current
    platform usage. update sizing therefore accounts only for the
    replacement staging requirement plus operation overhead; the
    rollback rename does not create another full artifact copy.
    """

    from core.config import (
        load_config,
    )

    from core.model_inventory import (
        list_model_inventory,
    )

    from core.model_remote_storage_preflight import (
        build_huggingface_storage_candidate,
    )

    from core.model_storage_requirements import (
        estimate_model_update_storage,
    )

    from core.model_update import (
        update_model,
    )

    from core.storage_commit_admission import (
        evaluate_storage_commit_admission,
    )

    from core.storage_operation_lock import (
        StorageOperationBusyError,
        storage_operation_lock,
    )

    from core.storage_planning import (
        build_storage_plan,
    )


    config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )


    overhead_fraction = float(
        settings.get(
            "model_operation_overhead_fraction",
            0.10,
        )
    )


    overhead_min_bytes = int(
        float(
            settings.get(
                "model_operation_overhead_min_gb",
                1.0,
            )
        )
        * (
            1024 ** 3
        )
    )


    try:
        with storage_operation_lock(
            "model_update_huggingface",

            config=config,
        ):

            inventory = (
                list_model_inventory()
            )


            current = next(
                (
                    item
                    for item in inventory[
                        "models"
                    ]
                    if item.get(
                        "model_id"
                    )
                    == model_id
                ),
                None,
            )


            #
            # Preserve the existing update_model validation semantics
            # for conditions that are known to fail before staging.
            #
            # Calling update_model here is safe because each of these
            # states exits before any mutation or staging directory is
            # created.
            #

            early_blocked = (
                current is None
            )


            if current is not None:

                management = (
                    current.get(
                        "management"
                    )
                    or {}
                )

                deployment = (
                    current.get(
                        "deployment"
                    )
                    or {}
                )

                source = (
                    current.get(
                        "source"
                    )
                    or {}
                )


                early_blocked = (
                    not management.get(
                        "managed",
                        False,
                    )

                    or deployment.get(
                        "selected"
                    )

                    or (
                        deployment.get(
                            "service_state"
                        )
                        == "running"
                    )

                    or (
                        deployment.get(
                            "load_state"
                        )
                        == "loaded"
                    )

                    or (
                        source.get(
                            "provider"
                        )
                        != "huggingface"
                    )

                    or not source.get(
                        "source_model_id"
                    )
                )


            if early_blocked:

                result = (
                    update_model(
                        model_id,

                        revision=revision,
                    )
                )


                if result.get(
                    "ok",
                    False,
                ):
                    raise RuntimeError(
                        "Early-blocked update unexpectedly "
                        "reached a successful mutation."
                    )


                return {
                    "ok": False,

                    "action": (
                        "update_model"
                    ),

                    "error": (
                        result[
                            "error"
                        ]
                    ),
                }


            source = (
                current.get(
                    "source"
                )
                or {}
            )


            provider = (
                source.get(
                    "provider"
                )
            )

            source_model_id = (
                source.get(
                    "source_model_id"
                )
            )


            #
            # Preserve transfer-enabled/provider-enabled semantics
            # before making the remote manifest request.
            #

            transfer_config = config.get(
                "model_transfer",
                {},
            )


            if not transfer_config.get(
                "enabled",
                False,
            ):
                return {
                    "ok": False,

                    "action": (
                        "update_model"
                    ),

                    "error": {
                        "code": (
                            "transfer_disabled"
                        ),

                        "detail": (
                            "Model transfer is disabled."
                        ),
                    },
                }


            if provider not in transfer_config.get(
                "providers",
                [],
            ):
                return {
                    "ok": False,

                    "action": (
                        "update_model"
                    ),

                    "error": {
                        "code": (
                            "provider_not_enabled"
                        ),

                        "detail": (
                            "ModelTransfer provider "
                            + repr(
                                provider
                            )
                            + " is not enabled."
                        ),
                    },
                }


            #
            # Resolve requested branch/tag/revision to the immutable
            # repository revision whose exact bytes will be admitted.
            #

            try:
                replacement = (
                    build_huggingface_storage_candidate(
                        source_model_id,

                        revision=revision,
                    )
                )

            except RuntimeError as exc:

                return {
                    "ok": False,

                    "action": (
                        "update_model"
                    ),

                    "error": {
                        "code": (
                            "storage_preflight_failed"
                        ),

                        "detail": str(
                            exc
                        ),
                    },
                }


            manifest = (
                replacement.get(
                    "remote_manifest"
                )
                or {}
            )


            if not manifest.get(
                "resolved",
                False,
            ):
                return {
                    "ok": False,

                    "action": (
                        "update_model"
                    ),

                    "error": {
                        "code": (
                            "storage_preflight_failed"
                        ),

                        "detail": (
                            "Hugging Face replacement manifest "
                            "could not be resolved completely."
                        ),

                        "reason": (
                            manifest.get(
                                "exactness"
                            )
                        ),
                    },

                    "remote_manifest": (
                        manifest
                    ),
                }


            immutable_revision = (
                replacement[
                    "source"
                ][
                    "revision"
                ]
            )


            requirement = (
                estimate_model_update_storage(
                    current,

                    replacement,

                    overhead_fraction=(
                        overhead_fraction
                    ),

                    overhead_min_bytes=(
                        overhead_min_bytes
                    ),
                )
            )


            storage_plan = (
                build_storage_plan(
                    config=config,

                    calibrate_if_required=False,
                )
            )


            admission = (
                evaluate_storage_commit_admission(
                    requirement,

                    config=config,

                    storage_plan=(
                        storage_plan
                    ),
                )
            )


            if not admission.get(
                "allowed",
                False,
            ):
                return {
                    "ok": False,

                    "action": (
                        "update_model"
                    ),

                    "error": {
                        "code": (
                            "storage_admission_denied"
                        ),

                        "detail": (
                            "Model update was denied by "
                            "commit-time storage admission."
                        ),

                        "reason": (
                            admission.get(
                                "reason"
                            )
                        ),
                    },

                    "storage_admission": (
                        admission
                    ),

                    "remote_manifest": (
                        manifest
                    ),
                }


            #
            # TOCTOU protection:
            #
            # update_model receives the exact immutable revision used
            # for manifest sizing and commit admission.
            #

            result = (
                update_model(
                    model_id,

                    revision=(
                        immutable_revision
                    ),
                )
            )


            if not result.get(
                "ok",
                False,
            ):
                return {
                    "ok": False,

                    "action": (
                        "update_model"
                    ),

                    "error": (
                        result[
                            "error"
                        ]
                    ),

                    "storage_admission": (
                        admission
                    ),

                    "remote_manifest": (
                        manifest
                    ),
                }


            #
            # Preserve the administrator's original requested
            # revision in the outward-facing result while retaining
            # the immutable preflight revision separately.
            #
            # Persistent Inventory is still written by update_model
            # using the actual resolved revision from the transfer.
            #

            result[
                "requested_revision"
            ] = revision

            result[
                "preflight_resolved_revision"
            ] = (
                immutable_revision
            )


            _invalidate_capacity_evidence_after_storage_mutation(
                "model_update_succeeded"
            )


            return {
                "ok": True,

                "action": (
                    "update_model"
                ),

                "result": result,

                "storage_admission": (
                    admission
                ),

                "remote_manifest": (
                    manifest
                ),
            }


    except StorageOperationBusyError as exc:

        return {
            "ok": False,

            "action": (
                "update_model"
            ),

            "error": {
                "code": (
                    "storage_operation_busy"
                ),

                "detail": str(
                    exc
                ),
            },
        }


