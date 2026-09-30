from datetime import UTC, date, datetime
from typing import Annotated, Any, ClassVar

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from mona.ids import is_id
from mona.naming import to_camel


class Dto(BaseModel):
    """camelCase JSON (C1 §1.1.2); fields named in `omit_if_none` are TS optional (`x?:`)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        extra="forbid",
    )
    omit_if_none: ClassVar[frozenset[str]] = frozenset()

    @model_serializer(mode="wrap")
    def _omit_absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        for name in self.omit_if_none:
            for key in (name, to_camel(name)):
                if key in data and data[key] is None:
                    del data[key]
        return data


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


Timestamp = Annotated[AwareDatetime, AfterValidator(_utc)]
Day = date


def _id_type(prefix: str) -> Any:
    def check(value: str) -> str:
        if not is_id(value, prefix):
            raise ValueError(f"expected a {prefix}_ id")
        return value

    return Annotated[str, AfterValidator(check)]


DocId = _id_type("doc")
EntityId = _id_type("ent")
SubUnitId = _id_type("sub")
PersonId = _id_type("per")
AccountId = _id_type("acc")
CounterpartyId = _id_type("cpt")
RuleId = _id_type("rul")
BatchId = _id_type("bat")
GroupId = _id_type("grp")
InterviewId = _id_type("int")
QuestionId = _id_type("qst")
DeadlineId = _id_type("ddl")
ReminderId = _id_type("rem")
DraftId = _id_type("drf")
ExportId = _id_type("exp")
