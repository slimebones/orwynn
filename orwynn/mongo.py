import typing
from contextlib import suppress
from copy import copy
from enum import Enum
from typing import Any, ClassVar, Generic, Iterable, Self, TypeVar

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import BaseModel
from pykit import validation
from pykit.err import NotFoundErr, UnsupportedErr
from pykit.func import FuncSpec
from pykit.log import log
from pykit.search import DbSearch
from pykit.types import T
from pymongo import MongoClient
from pymongo import ReturnDocument as ReturnDocStrat
from pymongo.cursor import Cursor as MongoCursor
from pymongo.database import Database as MongoDb
from rxcat import Evt, InpErr, Msg, MsgFilter, Req, code

from orwynn.cfg import Cfg
from orwynn.dto import TUdto, Udto
from orwynn.env import OrwynnEnvUtils
from orwynn.sys import Sys


def filter_collection_factory(collection: str) -> MsgFilter:
    """
    Filters incoming msg to have a certain collection.

    If msg doesn't have "collection" field (or it is set to None, the check is
    not performed and true is returned.

    If collection field exists, but it is not a str, true is returned,
    but warning is issued.
    """
    async def filter_collection(msg: Msg) -> bool:
        real_collection = getattr(msg, "collection", None)
        if real_collection is None:
            return True
        if not isinstance(real_collection, str):
            log.warn(
                f"{msg} uses \"collection\" field = {real_collection},"
                " which is not instance of str, and probably has not intention"
                " to connect it with database collection"
                " => return true from this filter"
            )
            return True
        return collection == real_collection

    return filter_collection

# We manage mongo CRUD by Create, Get, Upd and Del requests.
# Get and Del requests are ready-to-use and fcoded. Create and Upd requests
# are abstract, since we expect user to add custom fields to the req body.
#
# By Orwynn convention, we pub GotDocEvt/GotDocsEvt in response to
# Create/Get/Upd requests. Del req should receive only OkEvt, without doc
# payload.
#
# For "collection" field, the __default__ db is assumed. Later we might add
# redefine field to this, but now we're fine.

@code("orwynn.get-docs-req")
class GetDocsReq(Req):
    collection: str
    searchQuery: dict

@code("orwynn.got-doc-udto-evt")
class GotDocUdtoEvt(Evt, Generic[TUdto]):
    collection: str
    udto: TUdto

@code("orwynn.got-doc-udtos-evt")
class GotDocUdtosEvt(Evt, Generic[TUdto]):
    collection: str
    udtos: list[TUdto]

@code("orwynn.del-doc-req")
class DelDocReq(Req):
    collection: str
    searchQuery: dict

@code("orwynn.create-doc-req")
class CreateDocReq(Req):
    collection: str
    createQuery: dict

@code("orwynn.upd-doc-req")
class UpdDocReq(Req):
    collection: str
    searchQuery: dict
    updQuery: dict

MongoCompatibleType = str | int | float | bool | list | dict | None
MongoCompatibleTypes: tuple[Any, ...] = typing.get_args(MongoCompatibleType)

class MongoCfg(Cfg):
    url: str
    database_name: str
    must_clean_db_on_destroy: bool = False

class Doc(BaseModel):
    """
    Mapping to work with MongoDB.

    Itself is some model representing MongoDB document and also has some class
    methods to manipulate with related document in DB and translate it from/to
    mapping.

    The ID of the document on creating is always a string, not ObjectId for
    adjusting convenience. Under the hood a convertation str->ObjectId is
    performed before saving to MongoDB and backwards ObjectId->str before
    forming the document from MongoDB data.
    """
    sid: str = ""
    """
    String representation of mongo objectid. Set to empty string if is not
    synchronized with db yet.
    """

    _cached_collection_name: ClassVar[str | None] = None

    @classmethod
    def to_udtos(cls, docs: list[Self]) -> list[Udto]:
        return [doc.to_udto() for doc in docs]

    @classmethod
    def to_got_doc_udtos_evt(
        cls,
        req: Req,
        docs: list[Self],
        *,
        override_to_connids: list[int] | None = None
    ) -> GotDocUdtosEvt:
        udtos = cls.to_udtos(docs)
        rsid = req.msid

        to_connids = []
        if override_to_connids:
            to_connids = override_to_connids
        elif req.m_connid is not None:
            to_connids = [req.m_connid]

        return GotDocUdtosEvt(
            rsid=rsid,
            m_toConnids=to_connids,
            collection=cls.get_collection(),
            udtos=udtos
        )

    def to_udto(self) -> Udto:
        raise NotImplementedError

    def to_got_doc_udto_evt(
        self,
        req: Req,
        *,
        override_to_connids: list[int] | None = None
    ) -> GotDocUdtoEvt:
        rsid = req.msid

        to_connids = []
        if override_to_connids:
            to_connids = override_to_connids
        elif req.m_connid is not None:
            to_connids = [req.m_connid]

        return GotDocUdtoEvt(
            rsid=rsid,
            m_toConnids=to_connids,
            collection=self.get_collection(),
            udto=self.to_udto()
        )

    @classmethod
    def get_collection(cls) -> str:
        if not cls._cached_collection_name:
            name = cls.__name__
            assert len(name) > 0
            if len(name) == 1:
                name = name.lower()
            else:
                # camel case
                name = name[0].lower() + name[1:]
            cls._cached_collection_name = name
        return cls._cached_collection_name

    @classmethod
    def get_many(
        cls,
        query: dict | None = None,
        **kwargs
    ) -> Iterable[Self]:
        """
        Fetches all instances matching the query for this document.

        Args:
            query(optional):
                MongoDB-compliant dictionary to search. By default all
                instances of the document is fetched.
            **kwargs(optional):
                Additional arguments to Mongo's find method.

        Returns:
            Iterable with the results of the search.
        """
        _query: dict = cls._parse_query(query)
        validation.validate(_query, dict)

        cursor: MongoCursor = MongoUtils.get_many(
            cls.get_collection(),
            cls._adjust_sid_to_mongo(_query),
            **kwargs
        )

        return map(cls._parse_data_to_doc, cursor)

    @classmethod
    def try_get(
        cls,
        query: dict,
        **kwargs
    ) -> Self | None:
        validation.validate(query, dict)

        data = MongoUtils.try_get(
            cls.get_collection(),
            cls._adjust_sid_to_mongo(query),
            **kwargs
        )
        if data is None:
            return None

        return cls._parse_data_to_doc(data)

    def create(self, **kwargs) -> Self:
        dump: dict = self._adjust_sid_to_mongo(self.model_dump())
        return self._parse_data_to_doc(MongoUtils.create(
            self.get_collection(), dump, **kwargs
        ))

    @classmethod
    def try_get_and_del(
        cls,
        query: dict,
        **kwargs
    ) -> bool:
        return MongoUtils.try_del(
            cls.get_collection(),
            cls._adjust_sid_to_mongo(query),
            **kwargs
        )

    def delete(
        self,
        **kwargs
    ):
        if not self.sid:
            raise InpErr(f"unsync doc {self}")
        return MongoUtils.delete(
            self.get_collection(),
            {"_id": MongoUtils.convert_to_object_id(self.sid)},
            **kwargs
        )

    def try_del(
        self,
        **kwargs
    ) -> bool:
        if not self.sid:
            return False
        return MongoUtils.try_del(
            self.get_collection(),
            {"_id": MongoUtils.convert_to_object_id(self.sid)},
            **kwargs
        )

    @classmethod
    def get(cls, query: dict, **kwargs) -> Self:
        doc = cls.try_get(query, **kwargs)
        if doc is None:
            raise NotFoundErr(cls, query)
        return doc

    @classmethod
    def get_and_upd(
        cls,
        search_query: dict,
        upd_query: dict,
        *,
        search_kwargs: dict | None = None,
        upd_kwargs: dict | None = None
    ) -> Self:
        doc = cls.get(search_query, **search_kwargs or {})
        return doc.upd(upd_query, **upd_kwargs or {})

    def upd(
        self,
        query: dict,
        **kwargs
    ) -> Self:
        f = self.try_upd(query, **kwargs)
        if f is None:
            raise ValueError(f"failed to upd doc {self}, using query {query}")
        return f

    def try_upd(
        self,
        query: dict,
        **kwargs
    ) -> Self | None:
        """
        Updates document with given query.
        """
        if not self.sid:
            return None

        data = MongoUtils.try_upd(
            self.get_collection(),
            {"_id": MongoUtils.convert_to_object_id(self.sid)},
            query,
            **kwargs
        )
        if data is None:
            return None

        return self._parse_data_to_doc(data)

    def try_set(
        self,
        set_query: dict,
        **kwargs
    ) -> Self | None:
        return self.try_upd({"$set": set_query}, **kwargs)

    def try_inc(
        self,
        inc_query: dict,
        **kwargs
    ) -> Self | None:
        return self.try_upd({"$inc": inc_query}, **kwargs)

    def refresh(
        self
    ) -> Self:
        """
        Refreshes the document with a new data from the database.
        """
        if not self.sid:
            raise InpErr("empty sid")
        query = {"sid": self.sid}
        f = self.try_get(query)
        if f is None:
            raise NotFoundErr(type(self), query)
        return f

    @classmethod
    def _parse_data_to_doc(cls, data: dict) -> Self:
        """Parses document to specified Model."""
        return cls.model_validate(cls._adjust_sid_from_mongo(data))

    @staticmethod
    def _parse_query(query: dict | None) -> dict:
        return {} if query is None else copy(query)

    @classmethod
    def _adjust_sid_to_mongo(cls, data: dict) -> dict:
        if "sid" in data and data["sid"]:
            input_sid_value: Any = data["sid"]
            if input_sid_value is not None:
                if (
                    isinstance(input_sid_value, (str, dict, list))
                ):
                    data["_id"] = MongoUtils.convert_to_object_id(
                        input_sid_value
                    )
                else:
                    raise UnsupportedErr(
                        f"field \"sid\" with value {input_sid_value}"
                    )
            del data["sid"]
        return data

    @staticmethod
    def _adjust_sid_from_mongo(data: dict) -> dict:
        if "_id" in data:
            if data["_id"] is not None:
                data["sid"] = str(data["_id"])
            del data["_id"]
        return data

TDoc = TypeVar("TDoc", bound=Doc)

class MongoSys(Sys[MongoCfg]):
    async def init(self):
        self._client: MongoClient = MongoClient(self._cfg.url)
        self._db: MongoDb = self._client[self._cfg.database_name]
        await MongoUtils.init(self._client, self._db)

    async def destroy(self):
        if self._cfg.must_clean_db_on_destroy:
            MongoUtils.drop_db()

class MongoUtils:
    _client: MongoClient
    _db: MongoDb

    @classmethod
    async def init(cls, client: MongoClient, db: MongoDb):
        cls._client = client
        cls._db = db

    @classmethod
    async def destroy(cls):
        with suppress(AttributeError):
            del cls._client
        with suppress(AttributeError):
            del cls._db

    @classmethod
    def drop_db(cls):
        if not OrwynnEnvUtils.is_debug():
            log.err("decline db clean - ORWYNN_DEBUG is not set to 1")
            return
        if not OrwynnEnvUtils.is_clean_allowed():
            log.err("decline db clean - ORWYNN_ALLOW_CLEAN is not set to 1")
            return
        cls._client.drop_database(cls._db)

    @classmethod
    def try_get(
        cls,
        collection: str,
        query: dict,
        **kwargs
    ) -> dict | None:
        validation.validate(collection, str)
        validation.validate(query, dict)

        result: Any | None = cls._db[collection].find_one(
            query, **kwargs
        )

        if result is None:
            return None

        assert isinstance(result, dict)
        return result

    @classmethod
    def get_many(
        cls,
        collection: str,
        query: dict,
        **kwargs
    ) -> MongoCursor:
        validation.validate(collection, str)
        validation.validate(query, dict)

        return cls._db[collection].find(
            query, **kwargs
        )

    @classmethod
    def create(
        cls,
        collection: str,
        data: dict,
        **kwargs
    ) -> dict:
        validation.validate(collection, str)
        validation.validate(data, dict)

        inserted_id: str = cls._db[collection].insert_one(
            data,
            **kwargs
        ).inserted_id

        # instead of searching for created document, just replace it's id
        # with mongo's generated one, which is better for performance
        copied: dict = data.copy()
        copied["_id"] = inserted_id
        return copied

    @classmethod
    def try_upd(
        cls,
        collection: str,
        query: dict,
        operation: dict,
        **kwargs
    ) -> dict | None:
        """Updates a document matching query and returns updated version."""
        validation.validate(collection, str)
        validation.validate(query, dict)
        validation.validate(operation, dict)

        upd_doc: Any = \
            cls._db[collection].find_one_and_update(
                query,
                operation,
                return_document=ReturnDocStrat.AFTER,
                **kwargs
            )

        if upd_doc is None:
            return None

        assert isinstance(upd_doc, dict)
        return upd_doc

    @classmethod
    def delete(
        cls,
        collection: str,
        query: dict,
        **kwargs
    ):
        validation.validate(collection, str)
        validation.validate(query, dict)

        del_result = cls._db[collection].delete_one(
            query,
            **kwargs
        )

        if del_result.deleted_count == 0:
            raise NotFoundErr(f"doc in collection {collection}", query)

    @classmethod
    def try_del(
        cls,
        collection: str,
        query: dict,
        **kwargs
    ) -> bool:
        validation.validate(collection, str)
        validation.validate(query, dict)

        del_result = cls._db[collection].delete_one(
            query,
            **kwargs
        )

        return del_result.deleted_count > 0

    @staticmethod
    def process_search(
        query: dict[str, Any],
        search: "DocSearch[TDoc]",
        doc_type: type[TDoc],
        *,
        find_all_kwargs: dict | None = None,
    ) -> list[TDoc]:
        if find_all_kwargs is None:
            find_all_kwargs = {}

        result: list[TDoc] = list(doc_type.get_many(
            query,
            **find_all_kwargs,
        ))

        if len(result) == 0:
            raise search.get_not_found_error("TDoc")
        if search.expectation is not None:
            search.expectation.check(result)

        return result

    @staticmethod
    def query_by_nested_dict(
        query: dict[str, Any],
        nested_dict: dict[str, Any],
        root_key: str,
    ) -> None:
        """
        Updates query for searching nested dict values.

        Args:
            query:
                Query to update.
            nested_dict:
                Data to search.
            root_key:
                Outermost key of field containing the nested dict.

        Example:
        ```python
        class MyDoc(Doc):
            mydata: dict

        query = {}
        nd = {
            "mycode": {
                "approximate": {
                    "$in": [12, 34]
                }
            }
        }
        root_key = "mydata"

        MongoUtils.query_by_nested_dict(
            query,
            nd,
            root_key
        )
        # query = {"mydata.mycode.approximate": {"$in": [12, 34]}}
        ```
        """
        converted_data: dict[str, Any] = MongoUtils.convert_dict({
            root_key: nested_dict,
        })
        query.update(converted_data)

    @staticmethod
    def convert_dict(d: dict[str, Any]) -> dict[str, Any]:
        """
        Converts dictionary into a Mongo search format.

        All key structures is converted to dot-separated string, e.g.
        `{"key1": {"key2": {"key3_1": 10, "key3_2": 20}}}` is converted to
        `{"key1.key2.key3_1": 10, "key1.key2.key3_2": 20}`.

        Keys started with dollar sign are not converted and left as it is:
        ```python
        # input
        {
            "a1": {
                "a2": {
                    "$in": my_list
                }
            }
        }

        # output
        {
            "a1.a2": {
                "$in": my_list
            }
        }
        ```
        """
        result: dict[str, Any] = {}

        for k, v in d.items():

            if k.startswith("$") or not isinstance(v, dict):
                result[k] = v
                continue

            for k1, v1 in MongoUtils.convert_dict(v).items():
                if k1.startswith("$"):
                    result[k] = {
                        k1: v1,
                    }
                    continue
                result[k + "." + k1] = v1

        return result

    @staticmethod
    def convert_compatible(obj: Any) -> MongoCompatibleType:
        """
        Converts object to mongo compatible type.

        Convertation rules:
        - object with type listed in already compatible mongo types is returned
        as it is
        - elements of list, as well as dictionary's keys and values are
        converted recursively using this function
        - in case of Enum, the Enum's value is obtained and converted through
        this function
        - objects with defined attribute `mongovalue` (either by variable or
        property) is called like `obj.mongovalue` and the result is converted
        again through this function
        - for all other types the MongoTypeConversionError is raised

        Args:
            obj:
                Object to convert.

        Raises:
            MongoTypeConversionError:
                Cannot convert object to mongo-compatible.
        """
        result: MongoCompatibleType

        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                result[MongoUtils.convert_compatible(k)] = \
                    MongoUtils.convert_compatible(v)
        elif isinstance(obj, list):
            result = []
            for item in obj:
                result.append(MongoUtils.convert_compatible(item))
        elif type(obj) in MongoCompatibleTypes:
            result = obj
        elif hasattr(obj, "mongovalue"):
            result = MongoUtils.convert_compatible(obj.mongovalue)
        elif isinstance(obj, Enum):
            result = MongoUtils.convert_compatible(obj.value)
        else:
            raise ValueError(f"cannot convert {type(obj)}")

        return result

    @classmethod
    def convert_to_object_id(cls, obj: T) -> T | ObjectId:
        """
        Converts an object to ObjectId compliant.

        If the object is:
        - string: It is passed directly to ObjectId()
        - dict: All values are recursively converted using this method.
        - list: All items are recursively converted using this method.
        - other types: Nothing will be done.

        Returns:
            ObjectId-compliant representation of the given object.
        """
        result: T | ObjectId

        if isinstance(obj, str):
            try:
                result = ObjectId(obj)
            except InvalidId as error:
                raise ValueError(
                    f"{obj} is invalid id"
                ) from error
        elif isinstance(obj, dict):
            result = type(obj)()
            for k, v in obj.items():
                result[k] = MongoUtils.convert_to_object_id(v)
        elif isinstance(obj, list):
            result = type(obj)([
                MongoUtils.convert_to_object_id(x) for x in obj
            ])
        else:
            result = obj

        return result

class DocSearch(DbSearch[Doc], Generic[TDoc]):
    """
    Search Mongo Docs.
    """

class MongoStateFlagDoc(Doc):
    key: str
    value: bool

class MongoStateFlagSearch(DocSearch):
    keys: list[str] | None = None
    values: list[bool] | None = None

class MongoStateFlagUtils:
    @classmethod
    def get(
        cls,
        search: MongoStateFlagSearch
    ) -> list[MongoStateFlagDoc]:
        query: dict[str, Any] = {}

        if search.ids:
            query["id"] = {
                "$in": search.ids
            }
        if search.keys:
            query["key"] = {
                "$in": search.keys
            }
        if search.values:
            query["value"] = {
                "$in": search.values
            }

        return MongoUtils.process_search(
            query,
            search,
            MongoStateFlagDoc
        )

    @classmethod
    def get_first_or_set_default(
        cls,
        key: str,
        default_value: bool
    ) -> MongoStateFlagDoc:
        """
        Returns first flag found for given search or a new flag initialized
        with default value.
        """
        try:
            return cls.get(MongoStateFlagSearch(
                keys=[key]
            ))[0]
        except NotFoundErr:
            return cls.set(
                key,
                default_value
            )

    @classmethod
    def set(
        cls,
        key: str,
        value: bool
    ) -> MongoStateFlagDoc:
        """
        Sets new value for a key.

        If the key does not exist, create a new state flag with given value.
        """
        flag: MongoStateFlagDoc

        try:
            flag = cls.get(MongoStateFlagSearch(
                keys=[key]
            ))[0]
        except NotFoundErr:
            flag = MongoStateFlagDoc(key=key, value=value).create()
        else:
            flag = flag.upd({"$set": {"value": value}})

        return flag

    @classmethod
    def decide(
        cls,
        *,
        key: str,
        on_true: FuncSpec | None = None,
        on_false: FuncSpec | None = None,
        finally_set_to: bool,
        default_flag_on_not_found: bool
    ) -> Any:
        """
        Takes an action based on flag retrieved value.

        Args:
            key:
                Key of the flag to search for.
            finally_set_to:
                To which value the flag should be set after the operation is
                done.
            default_flag_on_not_found:
                Which value is to set for the unexistent by key flag.
            on_true(optional):
                Function to be called if the flag is True. Nothing is called
                by default.
            on_false(optional):
                Function to be called if the flag is False. Nothing is called
                by default.

        Returns:
            Chosen function output. None if no function is used.
        """
        result: Any = None
        flag: MongoStateFlagDoc = cls.get_first_or_set_default(
            key, default_flag_on_not_found
        )

        if flag.value is True and on_true is not None:
            result = on_true.call()
        if flag.value is False and on_false is not None:
            result = on_false.call()

        flag.upd({
            "set": {
                "value": finally_set_to
            }
        })

        return result

