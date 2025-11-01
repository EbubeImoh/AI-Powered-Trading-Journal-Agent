"""
Utility wrapper for storing OAuth tokens and analysis reports in DynamoDB.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import boto3
from boto3.dynamodb.conditions import Key

from app.core.config import AWSSettings


class DynamoDBClient:
    """Simple CRUD operations for token and report storage."""

    def __init__(self, settings: AWSSettings) -> None:
        self._settings = settings
        self._resource = boto3.resource("dynamodb", region_name=settings.region_name)
        self._table = self._resource.Table(settings.dynamodb_table_name)

    def put_item(self, item: Dict[str, Any]) -> None:
        """Put an item in the DynamoDB table."""
        self._table.put_item(Item=item)

    def get_item(self, partition_key: str, sort_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve an item using its key."""
        key: Dict[str, Any] = {"pk": partition_key}
        if sort_key is not None:
            key["sk"] = sort_key
        response = self._table.get_item(Key=key)
        return response.get("Item")

    def query_items(self, partition_key: str) -> list[Dict[str, Any]]:
        """Query items that share the same partition key."""
        response = self._table.query(KeyConditionExpression=Key("pk").eq(partition_key))
        return response.get("Items", [])


__all__ = ["DynamoDBClient"]
