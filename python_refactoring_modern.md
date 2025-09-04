# Modern Python 3.12+ Refactoring Guide

Based on classic refactoring patterns from Martin Fowler's catalog, adapted for modern Python 3.12+ features and best practices.

## Code Smells

### Bloaters

Code that has grown too large or complex to be easily handled.

#### Long Method

**Problem**: A method that's grown too long and complex.

**Modern Python Solution**:

```python
# Bad - Long method doing multiple things
def process_user_data(user_dict: dict[str, Any]) -> dict[str, Any]:
    # Validation (20+ lines)
    if not user_dict.get("email"):
        raise ValueError("Email required")
    # ... more validation

    # Transformation (15+ lines)
    normalized_email = user_dict["email"].lower().strip()
    # ... more transformation

    # Business logic (25+ lines)
    if user_dict.get("age", 0) < 18:
        # ... complex logic

    return processed_data

# Good - Extract methods with type hints and descriptive names
def process_user_data(user_dict: dict[str, Any]) -> dict[str, Any]:
    _validate_user_data(user_dict)
    normalized_data = _normalize_user_data(user_dict)
    return _apply_business_rules(normalized_data)

def _validate_user_data(user_dict: dict[str, Any]) -> None:
    """Validate required user fields."""
    if not user_dict.get("email"):
        raise ValueError("Email required")

def _normalize_user_data(user_dict: dict[str, Any]) -> dict[str, Any]:
    """Normalize user data formats."""
    return {
        **user_dict,
        "email": user_dict["email"].lower().strip(),
    }

def _apply_business_rules(user_data: dict[str, Any]) -> dict[str, Any]:
    """Apply business-specific processing rules."""
    # Business logic here
    return user_data
```

#### Large Class

**Problem**: A class trying to do too much.

**Modern Python Solution**:

```python
# Bad - God class
class UserManager:
    def authenticate(self, credentials: dict) -> bool: ...
    def validate_email(self, email: str) -> bool: ...
    def hash_password(self, password: str) -> str: ...
    def send_email(self, to: str, subject: str, body: str) -> None: ...
    def log_activity(self, activity: str) -> None: ...
    def generate_report(self) -> str: ...

# Good - Separated responsibilities with modern Python features
@dataclass
class User:
    email: str
    password_hash: str
    created_at: datetime = field(default_factory=datetime.now)

class UserAuthenticator:
    def authenticate(self, credentials: dict[str, str]) -> bool: ...
    def hash_password(self, password: str) -> str: ...

class EmailService:
    def validate_email(self, email: str) -> bool: ...
    def send_email(self, to: str, subject: str, body: str) -> None: ...

class ActivityLogger:
    def log_activity(self, user_id: str, activity: str) -> None: ...

class UserReportGenerator:
    def generate_report(self, users: list[User]) -> str: ...
```

#### Primitive Obsession

**Problem**: Using primitive types instead of meaningful objects.

**Modern Python Solution**:

```python
# Bad - Using primitives everywhere
def create_user(email: str, phone: str, age: int) -> dict:
    if "@" not in email:  # Primitive validation scattered everywhere
        raise ValueError("Invalid email")
    return {"email": email, "phone": phone, "age": age}

# Good - Value objects with validation
from typing import Self

@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        if "@" not in self.value or "." not in self.value.split("@")[1]:
            raise ValueError(f"Invalid email: {self.value}")

    @classmethod
    def from_string(cls, email_str: str) -> Self:
        return cls(email_str.lower().strip())

@dataclass(frozen=True)
class PhoneNumber:
    value: str

    def __post_init__(self) -> None:
        # Phone validation logic
        pass

@dataclass(frozen=True)
class Age:
    value: int

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 150:
            raise ValueError(f"Invalid age: {self.value}")

@dataclass
class User:
    email: Email
    phone: PhoneNumber
    age: Age
```

### Object-Orientation Abusers

#### Switch Statements / Match Cases

**Problem**: Complex conditional logic that should use polymorphism.

**Modern Python Solution**:

```python
# Bad - Complex match statement
def calculate_shipping(shipping_type: str, weight: float, distance: float) -> float:
    match shipping_type:
        case "standard":
            return weight * 0.5 + distance * 0.1
        case "express":
            return weight * 1.0 + distance * 0.2 + 10.0
        case "overnight":
            return weight * 2.0 + distance * 0.5 + 25.0
        case _:
            raise ValueError(f"Unknown shipping type: {shipping_type}")

# Good - Polymorphism with Protocol (modern Python)
from typing import Protocol

class ShippingCalculator(Protocol):
    def calculate(self, weight: float, distance: float) -> float: ...

@dataclass
class StandardShipping:
    def calculate(self, weight: float, distance: float) -> float:
        return weight * 0.5 + distance * 0.1

@dataclass
class ExpressShipping:
    def calculate(self, weight: float, distance: float) -> float:
        return weight * 1.0 + distance * 0.2 + 10.0

@dataclass
class OvernightShipping:
    def calculate(self, weight: float, distance: float) -> float:
        return weight * 2.0 + distance * 0.5 + 25.0

# Factory with type safety
def get_shipping_calculator(shipping_type: str) -> ShippingCalculator:
    calculators: dict[str, ShippingCalculator] = {
        "standard": StandardShipping(),
        "express": ExpressShipping(),
        "overnight": OvernightShipping(),
    }
    if shipping_type not in calculators:
        raise ValueError(f"Unknown shipping type: {shipping_type}")
    return calculators[shipping_type]
```

### Change Preventers

#### Shotgun Surgery

**Problem**: Changes require modifications in many unrelated classes.

**Modern Python Solution**:

```python
# Bad - Configuration scattered everywhere
class DatabaseService:
    def connect(self):
        host = "localhost"  # Hardcoded config
        port = 5432
        return connect(host, port)

class CacheService:
    def connect(self):
        host = "localhost"  # Duplicated config
        port = 6379
        return connect(host, port)

# Good - Centralized configuration with modern features
from typing import Self
from functools import cached_property

@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    username: str = "user"
    password: str = field(repr=False, default="")

    @classmethod
    def from_env(cls) -> Self:
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            username=os.getenv("DB_USERNAME", "user"),
            password=os.getenv("DB_PASSWORD", ""),
        )

@dataclass(frozen=True)
class AppConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig.from_env)
    cache_host: str = field(default_factory=lambda: os.getenv("CACHE_HOST", "localhost"))
    cache_port: int = field(default_factory=lambda: int(os.getenv("CACHE_PORT", "6379")))

class DatabaseService:
    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config

    def connect(self) -> Connection:
        return connect(self.config.host, self.config.port)
```

### Dispensables

#### Duplicate Code

**Problem**: Same code structure repeated in multiple places.

**Modern Python Solution**:

```python
# Bad - Duplicate validation logic
def create_user(data: dict) -> User:
    if not data.get("email"):
        raise ValueError("Email is required")
    if not data.get("name"):
        raise ValueError("Name is required")
    if len(data.get("password", "")) < 8:
        raise ValueError("Password must be at least 8 characters")
    return User(**data)

def update_user(user: User, data: dict) -> User:
    if not data.get("email"):
        raise ValueError("Email is required")
    if not data.get("name"):
        raise ValueError("Name is required")
    # Duplicate validation logic
    return user.update(**data)

# Good - Extract validation with modern typing
from typing import TypedDict

class UserData(TypedDict):
    email: str
    name: str
    password: str

def validate_user_data(data: dict[str, Any]) -> UserData:
    """Validate and return typed user data."""
    errors: list[str] = []

    if not data.get("email"):
        errors.append("Email is required")
    if not data.get("name"):
        errors.append("Name is required")
    if len(data.get("password", "")) < 8:
        errors.append("Password must be at least 8 characters")

    if errors:
        raise ValueError("; ".join(errors))

    return UserData(
        email=data["email"],
        name=data["name"],
        password=data["password"]
    )

def create_user(data: dict[str, Any]) -> User:
    validated_data = validate_user_data(data)
    return User(**validated_data)

def update_user(user: User, data: dict[str, Any]) -> User:
    validated_data = validate_user_data(data)
    return user.update(**validated_data)
```

## Modern Python Refactoring Techniques

### Composing Methods

#### Extract Method with Type Hints

```python
# Before
def process_order(order_data: dict) -> dict:
    # Calculate total (10 lines of logic)
    total = 0
    for item in order_data["items"]:
        total += item["price"] * item["quantity"]
        if item.get("discount"):
            total -= item["discount"]

    # Apply taxes (8 lines of logic)
    tax_rate = 0.08
    if order_data["state"] == "CA":
        tax_rate = 0.0975
    tax_amount = total * tax_rate

    return {"total": total, "tax": tax_amount, "final": total + tax_amount}

# After - Extract methods with proper typing
def process_order(order_data: dict[str, Any]) -> dict[str, float]:
    subtotal = _calculate_subtotal(order_data["items"])
    tax_amount = _calculate_tax(subtotal, order_data["state"])

    return {
        "total": subtotal,
        "tax": tax_amount,
        "final": subtotal + tax_amount
    }

def _calculate_subtotal(items: list[dict[str, Any]]) -> float:
    """Calculate order subtotal including discounts."""
    return sum(
        item["price"] * item["quantity"] - item.get("discount", 0)
        for item in items
    )

def _calculate_tax(subtotal: float, state: str) -> float:
    """Calculate tax amount based on state."""
    tax_rates = {"CA": 0.0975, "NY": 0.08, "TX": 0.0625}
    tax_rate = tax_rates.get(state, 0.08)
    return subtotal * tax_rate
```

#### Replace Temp with Query (using cached_property)

```python
# Before - Temporary variables
class OrderProcessor:
    def __init__(self, order: Order) -> None:
        self.order = order

    def generate_invoice(self) -> str:
        base_price = self.order.quantity * self.order.item_price
        discount_factor = 0.95 if self.order.quantity > 100 else 1.0
        discounted_price = base_price * discount_factor

        return f"Invoice: ${discounted_price:.2f}"

# After - Query methods with caching
class OrderProcessor:
    def __init__(self, order: Order) -> None:
        self.order = order

    @cached_property
    def base_price(self) -> float:
        return self.order.quantity * self.order.item_price

    @cached_property
    def discount_factor(self) -> float:
        return 0.95 if self.order.quantity > 100 else 1.0

    @cached_property
    def discounted_price(self) -> float:
        return self.base_price * self.discount_factor

    def generate_invoice(self) -> str:
        return f"Invoice: ${self.discounted_price:.2f}"
```

### Moving Features Between Objects

#### Extract Class with Dataclasses

```python
# Before - Too many responsibilities
@dataclass
class Customer:
    name: str
    email: str
    phone: str
    address_street: str
    address_city: str
    address_state: str
    address_zip: str

    def get_full_address(self) -> str:
        return f"{self.address_street}, {self.address_city}, {self.address_state} {self.address_zip}"

    def validate_address(self) -> bool:
        return bool(self.address_street and self.address_city and self.address_state)

# After - Extracted Address class
@dataclass(frozen=True)
class Address:
    street: str
    city: str
    state: str
    zip_code: str

    def __str__(self) -> str:
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"

    def is_valid(self) -> bool:
        return bool(self.street and self.city and self.state)

@dataclass
class Customer:
    name: str
    email: str
    phone: str
    address: Address
```

### Organizing Data

#### Replace Data Value with Object (Modern Enums)

```python
# Before - String constants
class Order:
    def __init__(self, status: str) -> None:
        self.status = status  # "pending", "shipped", "delivered"

    def can_cancel(self) -> bool:
        return self.status in ["pending", "processing"]

# After - Enum with methods
from enum import StrEnum

class OrderStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

    def can_cancel(self) -> bool:
        return self in (OrderStatus.PENDING, OrderStatus.PROCESSING)

    def is_active(self) -> bool:
        return self != OrderStatus.CANCELLED

@dataclass
class Order:
    status: OrderStatus = OrderStatus.PENDING

    def cancel(self) -> None:
        if not self.status.can_cancel():
            raise ValueError(f"Cannot cancel order with status: {self.status}")
        self.status = OrderStatus.CANCELLED
```

### Simplifying Conditional Expressions

#### Replace Nested Conditionals with Guard Clauses

```python
# Before - Nested conditionals
def calculate_discount(customer: Customer, order: Order) -> float:
    if customer is not None:
        if customer.is_premium:
            if order.total > 100:
                if order.items_count > 5:
                    return 0.15
                else:
                    return 0.10
            else:
                return 0.05
        else:
            return 0.0
    else:
        return 0.0

# After - Guard clauses with early returns
def calculate_discount(customer: Customer | None, order: Order) -> float:
    """Calculate discount percentage based on customer and order."""
    if customer is None:
        return 0.0

    if not customer.is_premium:
        return 0.0

    if order.total <= 100:
        return 0.05

    if order.items_count > 5:
        return 0.15

    return 0.10
```

## Modern Python Best Practices for Refactoring

### Use Type Hints Everywhere

```python
from typing import Protocol, TypeVar, Generic
from collections.abc import Callable, Iterator

T = TypeVar('T')

class Repository(Protocol, Generic[T]):
    def find_by_id(self, id: str) -> T | None: ...
    def save(self, entity: T) -> T: ...
    def delete(self, entity: T) -> None: ...

class UserService:
    def __init__(self, repository: Repository[User]) -> None:
        self.repository = repository

    def get_user(self, user_id: str) -> User:
        user = self.repository.find_by_id(user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")
        return user
```

### Leverage dataclasses and frozen classes

```python
@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "USD"

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError("Cannot add different currencies")
        return Money(self.amount + other.amount, self.currency)

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"
```

### Use Context Managers for Resource Management

```python
# Before - Manual resource management
def process_file(filename: str) -> list[str]:
    file = open(filename)
    try:
        data = file.read()
        return data.splitlines()
    finally:
        file.close()

# After - Context manager with Path
from pathlib import Path

def process_file(filename: str | Path) -> list[str]:
    return Path(filename).read_text().splitlines()

# Custom context manager for complex resources
from contextlib import contextmanager

@contextmanager
def database_transaction(db: Database) -> Iterator[Transaction]:
    transaction = db.begin_transaction()
    try:
        yield transaction
        transaction.commit()
    except Exception:
        transaction.rollback()
        raise
```

This refactoring guide combines classic patterns with modern Python 3.12+ features like improved type hints, dataclasses, enums, and pattern matching to create cleaner, more maintainable code.

