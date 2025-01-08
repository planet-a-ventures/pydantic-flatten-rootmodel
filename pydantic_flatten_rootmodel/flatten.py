from types import UnionType
import warnings
from typing import (
    Any,
    List,
    TypeVar,
    TypedDict,
    Union,
    get_args,
    get_origin,
    Annotated,
    Optional,
    Literal,
)
from pydantic import BaseModel, Discriminator, Field, RootModel, create_model
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined


def is_annotated_with_union(o: Any):
    """
    Whether the passed object is annotated with the given type
    """
    if o is None:
        return False
    return is_annotated_type(o) and is_union_type(get_type_annotation(o))


def is_union_type(obj) -> bool:
    """
    Checks if the given object is a typing.Union or a types.UnionType.

    Args:
        obj: The object to check.

    Returns:
        bool: True if the object is a Union type, False otherwise.
    """
    return get_origin(obj) is Union or isinstance(obj, UnionType)


def is_annotated_type(obj) -> bool:
    return get_origin(obj) is Annotated


def is_union_or_annotated_with_union(o: Any) -> bool:
    """
    Whether the passed object is a union
    """
    if o is None:
        return False
    return is_union_type(o) or is_annotated_with_union(o)


def get_type_annotation(o: Annotated):
    return get_args(o)[0]


def is_root_model(m: type[BaseModel]):
    return issubclass(m, RootModel)


class FieldData(TypedDict):
    types: List[Any]
    present_count: int
    total: int
    infos: List[FieldInfo]


def get_class_vars(c: type[BaseModel]):
    return {
        k: v for k, v in c.__dict__.items() if not callable(v) and not k.startswith("_")
    }


def flatten_root_model(
    root_model: type[RootModel], retain_class_vars=False
) -> type[BaseModel]:
    """
    Given a RootModel that wraps a Union of Pydantic models, produce a new model that:
    - Identifies if the root is a union of models.
    - If a discriminator is provided:
      * If using `Field(discriminator="field_name")` on a field in each variant:
        The field_name becomes the discriminator field. That field will become a Literal of all possible values.
      * If using a `Discriminator` annotation (e.g. `Annotated[Union[Cat, Dog], Discriminator("pet_type")]`):
        The specified field or function is the discriminator.
        - If a function-based discriminator is used, log a warning, as dynamic discriminators
          mean the flattened model might not be strictly correct.
    - If no discriminator:
      All fields from all models are included. Fields that differ in type become union types.
      Fields missing in some models become optional.

    Parameters
    ----------
    root_model : type[BaseModel]
        The RootModel that may wrap a union of Pydantic models.
    retain_class_vars: boolean
        Whether to retain class variables of the union types and the root model. Clashing class vars are overwritten as follows: union order, then root model.
        E.g. For a root model X with union A and B, the resulting class vars are `{**a_vars,**b_vars,**x_vars}`

    Returns
    -------
    type[BaseModel]
        A new Pydantic model that represents the "flattened" union.
    """

    if not is_root_model(root_model):
        raise ValueError("Only RootModels are supported")

    # Extract the root type from the RootModel
    root_type = root_model.__annotations__.get("root")

    # If not a union, just return the original model
    if not is_union_or_annotated_with_union(root_type):
        return root_model

    union_types = get_args(root_type)

    # Attempt to find a discriminator from annotations (Discriminator object)
    # Discriminator objects appear if root_type is Annotated:
    # Annotated[Union[...], Discriminator(...)]
    discriminator_field_name = None
    discriminator_values = []
    dynamic_discriminator = False  # True if a Discriminator(func=...) is found

    if is_annotated_type(root_type):
        # Extract the union and the metadata
        annotated_args = get_args(root_type)  # (Union[Cat, Dog], Discriminator(...) )
        # The first arg should be the Union, subsequent args may be Discriminator objects
        potential_union = annotated_args[0]
        union_metadata = annotated_args[1:]
        # Find a Discriminator in the metadata
        for meta in union_metadata:
            if isinstance(meta, Discriminator):
                if callable(meta.discriminator):
                    dynamic_discriminator = True
                else:
                    discriminator_field_name = meta.discriminator
                break
        # Update union_types to the actual union if Annotated was used
        if is_union_type(potential_union):
            union_types = get_args(potential_union)

    if dynamic_discriminator:
        warnings.warn(
            "A Discriminator with a function was found. The dynamic nature of "
            "this discriminator may mean the flattened model is not strictly correct.",
            UserWarning,
        )

    # Gather fields from each variant
    variants_fields = []
    for t in union_types:
        if not hasattr(t, "model_fields"):
            continue
        variant_fields = t.model_fields
        variants_fields.append((t, variant_fields))

    if len(variants_fields) == 0:
        return root_model

    # Collect a set of all field names from all models
    all_field_names: set[str] = set()
    for _, fields in variants_fields:
        all_field_names.update(fields.keys())

    # For each field, gather types from all variants that have it
    field_data: dict[str, FieldData] = {}
    total_variants = len(union_types)

    union_class_vars = {}
    for field_name in all_field_names:
        types_for_field = []
        present_count = 0
        infos_for_field = []
        for t, fields in variants_fields:
            if retain_class_vars:
                union_class_vars = {**union_class_vars, **get_class_vars(t)}
            # print("class_vars", class_vars)
            if field_name in fields:
                f_info: FieldInfo = fields[field_name]
                f_type = f_info.annotation
                types_for_field.append(f_type)
                infos_for_field.append(f_info)
                present_count += 1
        field_data[field_name] = {
            "types": types_for_field,
            "present_count": present_count,
            "total": total_variants,
            "infos": infos_for_field,
        }

    # If we have a known discriminator field:
    if discriminator_field_name:
        # If not already collected from Discriminator annotation, try to get values from models
        if not discriminator_values or len(discriminator_values) == 0:
            # Attempt to derive discriminator values from the variants
            discriminator_values = []
            for t, fields in variants_fields:
                if discriminator_field_name not in fields:
                    raise ValueError(
                        f"Discriminator field '{discriminator_field_name}' not found in model {t}."
                    )
                disc_field = fields[discriminator_field_name]
                # We expect a constant default value
                if (
                    disc_field.default is None
                    or disc_field.default is PydanticUndefined
                ):
                    # This might be a dynamic scenario, we can still proceed but no literal
                    # Since a dynamic scenario is unusual, let's not fail here but note it.
                    warnings.warn(
                        f"Discriminator field '{discriminator_field_name}' in {t} does not have a fixed default value. "
                        "The flattened discriminator may not be strictly correct.",
                        UserWarning,
                    )
                    discriminator_values.append(disc_field.annotation)
                else:
                    discriminator_values.append(disc_field.default)

        # All values are non-None, we can form a Literal
        final_type = Literal[tuple(discriminator_values)]

        # Override the field data for the discriminator
        field_data[discriminator_field_name]["types"] = [final_type]
        field_data[discriminator_field_name]["present_count"] = total_variants

    # Construct the flattened model fields
    flattened_fields = {}
    for field_name, info in field_data.items():
        # this is not stable:
        # distinct_types = set(info["types"])
        distinct_types = list(dict.fromkeys(info["types"]))
        if len(distinct_types) == 1:
            final_type = distinct_types.pop()
        else:
            # Multiple distinct types -> Union of those types
            final_type = Union[tuple(distinct_types)]

        # If not all variants have this field, make it optional
        if info["present_count"] < info["total"]:
            final_type = Optional[final_type]

        i = collapse_field_infos(info["infos"])
        flattened_fields[field_name] = (final_type, i)

    # Create a new model with the combined fields
    FlattenedModel = create_model(f"Flattened{root_model.__name__}", **flattened_fields)

    if retain_class_vars:
        for key, value in union_class_vars.items():
            setattr(FlattenedModel, key, value)
        for key, value in get_class_vars(root_model).items():
            setattr(FlattenedModel, key, value)

    return FlattenedModel


def collapse_field_infos(fields: List[FieldInfo]) -> FieldInfo:
    """
    Collapses a list of FieldInfo objects into a single FieldInfo object by combining a subset of their attributes.
    First attribute of each Field wins if the target is not a list that can be extended.

    Args:
        fields (List[FieldInfo]): A list of FieldInfo objects to collapse.

    Returns:
        FieldInfo: A single collapsed FieldInfo object.
    """
    if not fields:
        raise ValueError("The fields list must not be empty.")

    if len(fields) == 1:
        return fields[0]

    collapsed_field = {
        "default": None,
        "default_factory": None,
        "title": None,
        "description": None,
        "alias": None,
        "alias_priority": None,
    }

    for field in fields:
        for k, v in collapsed_field.items():
            if v is None:
                collapsed_field[k] = getattr(field, k)
        if field.examples is not None:
            collapsed_field["examples"] = [
                *collapsed_field.get("examples", []),
                *field.examples,
            ]

    return Field(**collapsed_field)
