from typing import List, Dict, Optional, Any
from src.providers.project.api import WorkItemAPI
from src.providers.project.metadata import FieldMetadataProvider


class ProjectManager:
    def __init__(
        self,
        project_key: str,
        api_client: Optional[WorkItemAPI] = None,
        metadata_provider: Optional[FieldMetadataProvider] = None,
    ):
        self.project_key = project_key
        self.api = api_client or WorkItemAPI()
        self.metadata = metadata_provider or FieldMetadataProvider(api_client=self.api)

    async def get_active_tasks(self) -> List[Dict[str, Any]]:
        """
        Get all active tasks (in_progress) for the project.
        Returns a list of dictionaries with human-readable keys.
        """
        # Call API
        resp = await self.api.filter_work_items(
            project_key=self.project_key, status=["in_progress"], page_size=50
        )

        if not resp.is_success or not resp.data:
            return []

        # Get field mappings
        mappings = await self.metadata.get_field_mappings(self.project_key)

        # Simplify and Translate Data
        tasks = []
        for item in resp.data.items:
            task_data = {
                "id": item.id,
                "name": item.name,
                "type": item.work_item_type_key,
            }

            # Process custom fields
            for pair in item.field_value_pairs:
                key = pair.get("field_key")
                val = pair.get("field_value")
                if key is not None:
                    human_key = mappings.get(key, key)
                    if human_key is not None:
                        task_data[human_key] = val

            tasks.append(task_data)

        return tasks

    async def create_task(
        self,
        name: str,
        type_key: str = "task",
        template_id: Optional[int] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Create a task and return its ID.
        Supports human-readable keys in extra_fields.
        """
        # Translate human keys back to field_xxx
        field_value_pairs = []
        if extra_fields:
            rev_mappings = await self.metadata.get_reverse_mappings(self.project_key)
            for k, v in extra_fields.items():
                real_key = rev_mappings.get(k, k)
                field_value_pairs.append({"field_key": real_key, "field_value": v})

        resp = await self.api.create_work_item(
            project_key=self.project_key,
            name=name,
            type_key=type_key,
            template_id=template_id,
            field_value_pairs=field_value_pairs,
        )

        if not resp.is_success:
            raise Exception(f"Failed to create task: {resp.msg} (code {resp.code})")

        if resp.data is None:
            raise Exception("Failed to create task: No data returned")

        return resp.data
