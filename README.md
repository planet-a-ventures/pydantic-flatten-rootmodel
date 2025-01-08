# pydantic-flatten-rootmodel

Library to transform a [Pydantic](https://pydantic.dev/)
[RootModel](https://docs.pydantic.dev/latest/api/root_model/)
with discriminated unions into a flattened BaseModel.

```py
from pydantic_flatten_rootmodel import flatten_root_model

class Cat(BaseModel):
    pet_type: Annotated[Literal["cat"], Field()]
    meow: str


class Dog(BaseModel):
    pet_type: Annotated[Literal["dog"], Field()]
    bark: str

class Pet(RootModel[Cat | Dog]):
    root: Annotated[Cat | Dog, Field(discriminator="pet_type")]


FlattenedPet = flatten_root_model(Pet)
```

 would result in `FlattenedPet` to have this shape:

 ```py
 class FlattenedPet(BaseModel):
    pet_type: Annotated[Union[Literal["cat"], Literal["dog"]]]
    bark: Union[str, None]
    meow: Union[str, None]
 ```

 This can for example be leveraged by [dlt](https://dlthub.com) for it's
 [schema definition](https://dlthub.com/docs/general-usage/resource#define-a-schema-with-pydantic).
 Without flattening it, the discriminated union is not recognized correctly
 when setting up the table schema.
