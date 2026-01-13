import logging
from typing import Dict, List, Optional

from src.core.project_client import get_project_client

logger = logging.getLogger(__name__)


class WorkItemAPI:
    """
    飞书项目工作项 API 封装 (Data Layer)
    只负责底层 HTTP 调用，不含业务逻辑
    """

    def __init__(self):
        self.client = get_project_client()

    async def create(
        self,
        project_key: str,
        work_item_type_key: str,
        name: str,
        field_value_pairs: List[Dict],
        template_id: Optional[int] = None,
    ) -> int:
        """创建工作项"""
        logger.info("Creating work item: project_key=%s, type_key=%s, name=%s",
                   project_key, work_item_type_key, name)
        logger.debug("Field value pairs: %s", field_value_pairs)

        url = f"/open_api/{project_key}/work_item/create"
        payload = {
            "work_item_type_key": work_item_type_key,
            "name": name,
            "field_value_pairs": field_value_pairs,
        }
        if template_id:
            payload["template_id"] = template_id
            logger.debug("Using template_id=%d", template_id)

        resp = await self.client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("err_code") != 0:
            err_msg = data.get("err_msg", "Unknown error")
            logger.error("Create WorkItem failed: err_code=%s, err_msg=%s",
                        data.get("err_code"), err_msg)
            raise Exception(f"Create WorkItem failed: {err_msg}")

        issue_id = data.get("data")
        logger.info("Work item created successfully: issue_id=%s", issue_id)
        return issue_id

    async def query(
        self,
        project_key: str,
        work_item_type_key: str,
        work_item_ids: List[int],
        expand: Optional[Dict] = None,
    ) -> List[Dict]:
        """批量获取工作项详情"""
        logger.debug("Querying work items: project_key=%s, type_key=%s, ids=%s",
                    project_key, work_item_type_key, work_item_ids)

        url = f"/open_api/{project_key}/work_item/{work_item_type_key}/query"
        payload = {"work_item_ids": work_item_ids, "expand": expand or {}}
        resp = await self.client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("err_code") != 0:
            err_msg = data.get("err_msg", "Unknown error")
            logger.error("Query WorkItem failed: err_code=%s, err_msg=%s",
                        data.get("err_code"), err_msg)
            raise Exception(f"Query WorkItem failed: {err_msg}")

        items = data.get("data", [])
        logger.info("Query successful: retrieved %d work items", len(items))
        return items

    async def update(
        self,
        project_key: str,
        work_item_type_key: str,
        work_item_id: int,
        update_fields: List[Dict],
    ) -> None:
        """更新工作项"""
        logger.info("Updating work item: project_key=%s, type_key=%s, id=%d",
                   project_key, work_item_type_key, work_item_id)
        logger.debug("Update fields: %s", update_fields)

        url = f"/open_api/{project_key}/work_item/{work_item_type_key}/{work_item_id}"
        payload = {"update_fields": update_fields}
        resp = await self.client.put(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("err_code") != 0:
            err_msg = data.get("err_msg", "Unknown error")
            logger.error("Update WorkItem failed: err_code=%s, err_msg=%s",
                        data.get("err_code"), err_msg)
            raise Exception(f"Update WorkItem failed: {err_msg}")

        logger.info("Work item updated successfully: id=%d", work_item_id)

    async def delete(
        self, project_key: str, work_item_type_key: str, work_item_id: int
    ) -> None:
        """删除工作项"""
        logger.warning("Deleting work item: project_key=%s, type_key=%s, id=%d",
                      project_key, work_item_type_key, work_item_id)

        url = f"/open_api/{project_key}/work_item/{work_item_type_key}/{work_item_id}"
        resp = await self.client.delete(url)
        resp.raise_for_status()
        data = resp.json()
        if data.get("err_code") != 0:
            err_msg = data.get("err_msg", "Unknown error")
            logger.error("Delete WorkItem failed: err_code=%s, err_msg=%s",
                        data.get("err_code"), err_msg)
            raise Exception(f"Delete WorkItem failed: {err_msg}")

        logger.info("Work item deleted successfully: id=%d", work_item_id)

    async def filter(
        self,
        project_key: str,
        work_item_type_keys: List[str],
        page_num: int = 1,
        page_size: int = 20,
        expand: Optional[Dict] = None,
        **kwargs,
    ) -> Dict:
        """基础筛选"""
        logger.debug("Filtering work items: project_key=%s, type_keys=%s, page=%d/%d",
                   project_key, work_item_type_keys, page_num, page_size)
        logger.debug("Filter kwargs: %s", kwargs)

        url = f"/open_api/{project_key}/work_item/filter"
        payload = {
            "work_item_type_keys": work_item_type_keys,
            "page_num": page_num,
            "page_size": page_size,
            "expand": expand or {},
            **kwargs,
        }
        resp = await self.client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("err_code") != 0:
            err_msg = data.get("err_msg", "Unknown error")
            logger.error("Filter WorkItem failed: err_code=%s, err_msg=%s",
                        data.get("err_code"), err_msg)
            raise Exception(f"Filter WorkItem failed: {err_msg}")

        result = data.get("data", {})
        # 处理返回格式：可能是 list 或 dict
        if isinstance(result, list):
            items_count = len(result)
            logger.info("Filter successful: retrieved %d items (list format)", items_count)
            return result
        elif isinstance(result, dict):
            items_count = len(result.get("work_items", []))
            logger.info("Filter successful: retrieved %d items (dict format)", items_count)
            return result
        else:
            logger.warning(f"Unexpected result format: {type(result)}")
            return {"work_items": [], "pagination": {}}

    async def search_params(
        self,
        project_key: str,
        work_item_type_key: str,
        search_group: Dict,
        page_num: int = 1,
        page_size: int = 20,
        fields: Optional[List[str]] = None,
    ) -> Dict:
        """复杂条件搜索"""
        logger.debug("Searching work items with params: project_key=%s, type_key=%s, page=%d/%d",
                   project_key, work_item_type_key, page_num, page_size)
        logger.debug("Search group: %s", search_group)

        url = f"/open_api/{project_key}/work_item/{work_item_type_key}/search/params"
        payload = {
            "search_group": search_group,
            "page_num": page_num,
            "page_size": page_size,
        }
        if fields:
            payload["fields"] = fields
            logger.debug("Requested fields: %s", fields)

        resp = await self.client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("err_code") != 0:
            err_msg = data.get("err_msg", "Unknown error")
            logger.error("Search Params failed: err_code=%s, err_msg=%s",
                        data.get("err_code"), err_msg)
            raise Exception(f"Search Params failed: {err_msg}")

        result = data.get("data", {})
        # 兼容不同的 API 返回格式: data 可能是 dict 或 list
        if isinstance(result, list):
            # 如果 data 是 list，则直接作为 work_items
            result = {"work_items": result, "total": len(result)}
        items_count = len(result.get("work_items", []))
        logger.info("Search successful: retrieved %d items", items_count)
        return result

    async def batch_update(
        self,
        project_key: str,
        work_item_type_key: str,
        work_item_ids: List[int],
        update_fields: List[Dict],
    ) -> str:
        """批量更新工作项 (注意：Open API 仅支持单字段批量更新，这里我们封装一下，或者按 API 实际能力实现)

        API: /open_api/work_item/batch_update
        Body:
        {
            "project_key": "xxx",
            "work_item_type_key": "xxx",
            "work_item_ids": [1, 2],
            "field_key": "priority",
            "after_field_value": "option_2"
        }
        注意：该 API 每次只能更新一个字段。
        """
        url = "/open_api/work_item/batch_update"

        # 暂时只支持单个字段的批量更新，因为 API 限制
        # 如果传入多个字段，需要上层业务拆分调用
        if not update_fields or len(update_fields) > 1:
            raise NotImplementedError(
                "Batch update currently only supports single field update per call"
            )

        field = update_fields[0]

        payload = {
            "project_key": project_key,
            "work_item_type_key": work_item_type_key,
            "work_item_ids": work_item_ids,
            "field_key": field["field_key"],
            "after_field_value": field["field_value"],
        }

        logger.info("Batch updating work items: project_key=%s, type_key=%s, ids=%s, field=%s",
                   project_key, work_item_type_key, work_item_ids, field["field_key"])

        resp = await self.client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("err_code") != 0:
            err_msg = data.get("err_msg", "Unknown error")
            logger.error("Batch Update failed: err_code=%s, err_msg=%s",
                        data.get("err_code"), err_msg)
            raise Exception(f"Batch Update failed: {err_msg}")

        task_id = data.get("data")
        logger.info("Batch update successful: task_id=%s", task_id)
        return task_id  # 返回 task_id

    async def get_create_meta(self, project_key: str, work_item_type_key: str) -> Dict:
        """获取创建工作项的元数据

        对应 Postman: 工作项 > 工作项列表 > 获取创建工作项元数据
        API: GET /open_api/:project_key/work_item/:work_item_type_key/meta

        该接口返回创建工作项时需要填写的字段信息，包括:
        - 字段列表及其配置
        - 必填字段
        - 字段选项值
        - 默认值等

        Args:
            project_key: 项目空间 Key
            work_item_type_key: 工作项类型 Key (如 story, task, bug 等)

        Returns:
            创建工作项所需的元数据信息

        Raises:
            Exception: API 调用失败时抛出异常
        """
        url = f"/open_api/{project_key}/work_item/{work_item_type_key}/meta"

        logger.debug("Getting create meta: project_key=%s, type_key=%s",
                   project_key, work_item_type_key)

        resp = await self.client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if data.get("err_code") != 0:
            err_msg = data.get("err_msg", "Unknown error")
            logger.error("获取创建工作项元数据失败: err_code=%s, err_msg=%s",
                        data.get("err_code"), err_msg)
            raise Exception(f"获取创建工作项元数据失败: {err_msg}")

        meta = data.get("data", {})
        logger.debug("Retrieved create meta successfully")
        return meta
