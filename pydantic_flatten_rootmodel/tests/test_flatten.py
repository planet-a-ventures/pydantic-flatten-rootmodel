import json
from typing import Annotated, Any, List, Literal, TypeVar, Union
from pydantic import BaseModel, Discriminator, Field, RootModel, Tag

import pytest

from ..flatten import (
    collapse_field_infos,
    flatten_root_model,
    get_type_annotation,
    is_annotated_with_union,
    is_union_or_annotated_with_union,
)

from syrupy.extensions.json import JSONSnapshotExtension


@pytest.fixture
def snapshot_json(snapshot):
    return snapshot.with_defaults(extension_class=JSONSnapshotExtension)


def dump_model(m: BaseModel):
    return json.dumps(m.model_json_schema(mode="serialization"), indent=4)


def assert_model(m: BaseModel, snapshot):
    print("Original: ", dump_model(m))
    flattened_model = flatten_root_model(m)
    flattened = flattened_model.model_json_schema(mode="serialization")
    print("Flattened: ", json.dumps(flattened, indent=4))
    assert flattened == snapshot


class Cat(BaseModel):
    pet_type: Annotated[Literal["cat"], Field()]
    meow: str


class Dog(BaseModel):
    pet_type: Annotated[Literal["dog"], Field()]
    bark: str


def test_is_annotated_with_union():
    S = Annotated[Union[str, int], Field()]
    assert is_annotated_with_union(S)
    S = Annotated[str | int, Field()]
    assert is_annotated_with_union(S)


def test_is_union_or_annotated_with_union():
    U = Union[str, int]
    S = Annotated[U, Field()]
    assert is_union_or_annotated_with_union(U)
    assert is_union_or_annotated_with_union(S)


def test_get_type_annotation():
    T = TypeVar("T")
    assert get_type_annotation(Annotated[T, Field()]) is T


@pytest.mark.xfail(reason="We only support RootModel types", strict=True)
def test_non_root_models():
    flatten_root_model(Cat)


def test_identity_for_non_union_models():
    class X(RootModel[List[str]]):
        root: List[str]

    assert flatten_root_model(X) is X


@pytest.mark.parametrize("union_type", ["union", "pipe"])
def test_flatten_discriminator_field_root_model(
    union_type: Literal["union", "pipe"], snapshot_json
):

    match union_type:
        case "union":

            class Pet(RootModel[Union[Cat, Dog]]):
                root: Annotated[Union[Cat, Dog], Field(discriminator="pet_type")]

        case "pipe":

            class Pet(RootModel[Cat | Dog]):
                root: Annotated[Cat | Dog, Field(discriminator="pet_type")]

    assert_model(Pet, snapshot_json)


def test_flatten_discriminator_annotation_root_model(snapshot_json):

    class Pet(RootModel[Union[Cat, Dog]]):
        root: Annotated[Union[Cat, Dog], Discriminator("pet_type")]

    with pytest.warns(
        UserWarning, match="The flattened discriminator may not be strictly correct."
    ):
        assert_model(Pet, snapshot_json)


def test_aliases_retained(snapshot_json):
    class Cat(BaseModel):
        pet_type: Annotated[Literal["cat"], Field(alias="type")]
        meow: str

    class Dog(BaseModel):
        pet_type: Annotated[Literal["dog"], Field(alias="type")]
        bark: Annotated[str, Field(alias="grrrr")]

    class Pet(RootModel[Union[Cat, Dog]]):
        root: Annotated[Union[Cat, Dog], Field(discriminator="pet_type")]

    assert_model(Pet, snapshot_json)


def test_collapse_field_infos(snapshot):
    field = collapse_field_infos(
        [Field(examples=["bar"]), Field(alias="a"), Field(examples=["bla", "foo"])]
    )
    assert field == snapshot


def test_special_values(snapshot_json):
    class SpecialValue(BaseModel):
        value: int

    class DiscriminatedModel(RootModel):
        root: Annotated[
            (Annotated[int, Tag("int")] | Annotated["SpecialValue", Tag("model")]),
            Discriminator(lambda: 1 / 0),
        ]

    with pytest.warns(UserWarning, match="A Discriminator with a function was found"):
        assert flatten_root_model(DiscriminatedModel) is DiscriminatedModel


def test_class_vars_retained():
    raise NotImplementedError()


def test_None_type_discriminator():
    raise NotImplementedError()
