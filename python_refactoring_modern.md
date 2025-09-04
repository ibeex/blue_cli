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

## Complete Refactoring Techniques Reference

### Composing Methods

#### Inline Method
**Problem**: Method body is more obvious than the method name.

```python
# Before
def get_rating(self) -> int:
    return self._more_than_five_late_deliveries() * 2

def _more_than_five_late_deliveries(self) -> int:
    return 1 if self.late_deliveries > 5 else 0

# After
def get_rating(self) -> int:
    return (1 if self.late_deliveries > 5 else 0) * 2
```

#### Extract Variable
**Problem**: Complex expressions are hard to understand.

```python
# Before  
def calculate_total(self) -> float:
    return (self.quantity * self.item_price - 
            max(0, self.quantity - 500) * self.item_price * 0.05 +
            min(self.quantity * self.item_price * 0.1, 100.0))

# After
def calculate_total(self) -> float:
    base_price = self.quantity * self.item_price
    quantity_discount = max(0, self.quantity - 500) * self.item_price * 0.05
    shipping = min(base_price * 0.1, 100.0)
    return base_price - quantity_discount + shipping
```

#### Split Temporary Variable
**Problem**: Single variable used for multiple purposes.

```python
# Before
def calculate_trajectory(self) -> tuple[float, float]:
    temp = 2 * (self.height + self.width)
    print(f"Perimeter: {temp}")
    temp = self.height * self.width  # Variable reused!
    print(f"Area: {temp}")
    return temp, temp

# After
def calculate_trajectory(self) -> tuple[float, float]:
    perimeter = 2 * (self.height + self.width)
    print(f"Perimeter: {perimeter}")
    area = self.height * self.width
    print(f"Area: {area}")
    return perimeter, area
```

#### Remove Assignments to Parameters
**Problem**: Modifying parameters makes code confusing.

```python
# Before
def discount(input_val: float, quantity: int) -> float:
    if quantity > 50:
        input_val -= 2.0
    if quantity > 100:
        input_val -= 1.0
    return input_val

# After
def discount(input_val: float, quantity: int) -> float:
    result = input_val
    if quantity > 50:
        result -= 2.0
    if quantity > 100:
        result -= 1.0
    return result
```

#### Replace Method with Method Object
**Problem**: Long method with many local variables that can't be easily extracted.

```python
# Before - Complex method with many local variables
def calculate_gamma(self, input_val: int, quantity: int, year_to_date: int) -> int:
    important_value1 = input_val * quantity + self.delta()
    important_value2 = input_val * year_to_date + 100
    if year_to_date - important_value1 > 100:
        important_value2 -= 20
    important_value3 = important_value2 * 7
    # ... more complex logic with these variables
    return important_value3 - 2 * important_value1

# After - Extract to method object
@dataclass
class GammaCalculator:
    source: 'Account'
    input_val: int
    quantity: int
    year_to_date: int
    important_value1: int = 0
    important_value2: int = 0
    important_value3: int = 0

    def calculate(self) -> int:
        self.important_value1 = self.input_val * self.quantity + self.source.delta()
        self.important_value2 = self.input_val * self.year_to_date + 100
        self._apply_adjustments()
        self.important_value3 = self.important_value2 * 7
        return self.important_value3 - 2 * self.important_value1

    def _apply_adjustments(self) -> None:
        if self.year_to_date - self.important_value1 > 100:
            self.important_value2 -= 20

class Account:
    def calculate_gamma(self, input_val: int, quantity: int, year_to_date: int) -> int:
        return GammaCalculator(self, input_val, quantity, year_to_date).calculate()
```

### Moving Features Between Objects

#### Move Method
**Problem**: Method uses features of another class more than its own.

```python
# Before
@dataclass 
class Account:
    type: 'AccountType'
    days_overdrawn: int

    def overdraft_charge(self) -> float:
        if self.type.is_premium():
            result = 10
            if self.days_overdrawn > 7:
                result += (self.days_overdrawn - 7) * 0.85
            return result
        else:
            return self.days_overdrawn * 1.75

# After - Move method to AccountType
@dataclass
class AccountType:
    is_premium: bool

    def overdraft_charge(self, days_overdrawn: int) -> float:
        if self.is_premium:
            result = 10
            if days_overdrawn > 7:
                result += (days_overdrawn - 7) * 0.85
            return result
        else:
            return days_overdrawn * 1.75

@dataclass
class Account:
    type: AccountType
    days_overdrawn: int

    def overdraft_charge(self) -> float:
        return self.type.overdraft_charge(self.days_overdrawn)
```

#### Move Field
**Problem**: Field is used more by another class than its own.

```python
# Before
@dataclass
class Account:
    type: 'AccountType'
    interest_rate: float  # Used more by AccountType

    def interest_for_amount_days(self, amount: float, days: int) -> float:
        return self.interest_rate * amount * days / 365

@dataclass
class AccountType:
    pass

# After
@dataclass  
class AccountType:
    interest_rate: float

    def interest_for_amount_days(self, amount: float, days: int) -> float:
        return self.interest_rate * amount * days / 365

@dataclass
class Account:
    type: AccountType

    def interest_for_amount_days(self, amount: float, days: int) -> float:
        return self.type.interest_for_amount_days(amount, days)
```

#### Inline Class
**Problem**: Class isn't doing much and should be merged.

```python
# Before - TelephoneNumber class is too simple
@dataclass
class TelephoneNumber:
    area_code: str
    number: str

    def __str__(self) -> str:
        return f"({self.area_code}) {self.number}"

@dataclass
class Person:
    name: str
    telephone: TelephoneNumber

# After - Inline into Person
@dataclass  
class Person:
    name: str
    area_code: str
    phone_number: str

    def telephone_number(self) -> str:
        return f"({self.area_code}) {self.phone_number}"
```

#### Hide Delegate
**Problem**: Client calls delegate class directly.

```python
# Before - Client knows about Department
class Person:
    def __init__(self, name: str, department: 'Department') -> None:
        self.name = name
        self.department = department

class Department:
    def __init__(self, manager: 'Person') -> None:
        self.manager = manager

# Client code has to know about Department
manager = person.department.manager

# After - Hide the delegate
class Person:
    def __init__(self, name: str, department: 'Department') -> None:
        self.name = name
        self._department = department

    @property
    def manager(self) -> 'Person':
        return self._department.manager

# Client can work directly with Person  
manager = person.manager
```

### Organizing Data

#### Self Encapsulate Field
**Problem**: Direct field access makes it hard to add validation/transformation.

```python
# Before - Direct field access
@dataclass
class IntRange:
    low: int
    high: int

    def includes(self, arg: int) -> bool:
        return arg >= self.low and arg <= self.high

# After - Encapsulated with properties
class IntRange:
    def __init__(self, low: int, high: int) -> None:
        self._low = low
        self._high = high

    @property 
    def low(self) -> int:
        return self._low

    @low.setter
    def low(self, value: int) -> None:
        self._low = value

    @property
    def high(self) -> int:
        return self._high

    @high.setter  
    def high(self, value: int) -> None:
        self._high = value

    def includes(self, arg: int) -> bool:
        return arg >= self.low and arg <= self.high
```

#### Replace Array with Object
**Problem**: Array contains elements that mean different things.

```python
# Before - Array elements have different meanings
def performance_data() -> list[str]:
    return ["Liverpool", "15"]  # [name, wins]

# Client code
team_name = performance_data()[0]
wins = performance_data()[1]

# After - Dedicated object
@dataclass(frozen=True)
class Performance:
    name: str
    wins: int

def performance_data() -> Performance:
    return Performance("Liverpool", 15)

# Client code
perf = performance_data()
team_name = perf.name
wins = perf.wins
```

#### Encapsulate Collection
**Problem**: Method returns collection directly, allowing uncontrolled modification.

```python
# Before - Direct collection access
class Course:
    def __init__(self, name: str, is_advanced: bool) -> None:
        self.name = name
        self.is_advanced = is_advanced

class Person:
    def __init__(self) -> None:
        self._courses: list[Course] = []

    def courses(self) -> list[Course]:
        return self._courses  # Direct access allows mutation!

# After - Encapsulated collection
class Person:
    def __init__(self) -> None:
        self._courses: list[Course] = []

    @property
    def courses(self) -> tuple[Course, ...]:
        return tuple(self._courses)  # Immutable view

    def add_course(self, course: Course) -> None:
        self._courses.append(course)

    def remove_course(self, course: Course) -> None:
        self._courses.remove(course)

    def number_of_courses(self) -> int:
        return len(self._courses)
```

#### Replace Magic Number with Symbolic Constant
**Problem**: Numeric literals have unclear meaning.

```python
# Before
def potential_energy(self, mass: float, height: float) -> float:
    return mass * height * 9.81  # What is 9.81?

# After  
GRAVITATIONAL_CONSTANT = 9.81  # m/s²

def potential_energy(self, mass: float, height: float) -> float:
    return mass * height * GRAVITATIONAL_CONSTANT
```

### Simplifying Conditional Expressions

#### Consolidate Conditional Expression
**Problem**: Multiple conditions with same result.

```python
# Before
def disability_amount(self) -> float:
    if self.seniority < 2:
        return 0
    if self.months_disabled > 12:
        return 0  
    if self.is_part_time:
        return 0
    # Calculate disability amount...
    return self.base_amount * 0.8

# After
def disability_amount(self) -> float:
    if self._is_not_eligible_for_disability():
        return 0
    # Calculate disability amount...
    return self.base_amount * 0.8

def _is_not_eligible_for_disability(self) -> bool:
    return (self.seniority < 2 or 
            self.months_disabled > 12 or 
            self.is_part_time)
```

#### Consolidate Duplicate Conditional Fragments
**Problem**: Identical code in all branches.

```python
# Before
def calculate_charge(self) -> None:
    if self.is_special_deal():
        total = self.price * 0.95
        self.send_bill()  # Duplicate
    else:
        total = self.price * 0.98  
        self.send_bill()  # Duplicate

# After
def calculate_charge(self) -> None:
    if self.is_special_deal():
        total = self.price * 0.95
    else:
        total = self.price * 0.98
    self.send_bill()  # Moved out of conditional
```

#### Decompose Conditional
**Problem**: Complex conditional logic.

```python  
# Before
def calculate_charge(self, date: datetime, plan: Plan) -> float:
    if date.month < 4 or date.month > 10:
        charge = plan.summer_rate * self.usage
    else:
        charge = plan.winter_rate * self.usage + plan.service_charge
    return charge

# After
def calculate_charge(self, date: datetime, plan: Plan) -> float:
    if self._is_summer(date):
        charge = self._summer_charge(plan)
    else:
        charge = self._winter_charge(plan)
    return charge

def _is_summer(self, date: datetime) -> bool:
    return date.month < 4 or date.month > 10

def _summer_charge(self, plan: Plan) -> float:
    return plan.summer_rate * self.usage

def _winter_charge(self, plan: Plan) -> float:
    return plan.winter_rate * self.usage + plan.service_charge
```

#### Remove Control Flag  
**Problem**: Variable acting as control flag for loop.

```python
# Before
def check_security(self, people: list[str]) -> None:
    found = False
    for person in people:
        if not found:
            if person == "Don":
                self._send_alert()
                found = True
            if person == "John":  
                self._send_alert()
                found = True

# After
def check_security(self, people: list[str]) -> None:
    for person in people:
        if person in ("Don", "John"):
            self._send_alert()
            break
```

#### Introduce Null Object
**Problem**: Repeated null checks throughout code.

```python
# Before - Null checks everywhere
class Customer:
    def __init__(self, name: str) -> None:
        self.name = name

def get_plan(customer: Customer | None) -> str:
    if customer is None:
        return "basic"
    return customer.billing_plan

def get_history(customer: Customer | None) -> int:
    if customer is None:
        return 0  
    return customer.payment_history

# After - Null Object pattern
class Customer:
    def __init__(self, name: str) -> None:
        self.name = name
        
    @property
    def billing_plan(self) -> str:
        return "premium"
    
    @property    
    def payment_history(self) -> int:
        return 100

class NullCustomer(Customer):
    def __init__(self) -> None:
        super().__init__("occupant")
    
    @property
    def billing_plan(self) -> str:
        return "basic"
        
    @property
    def payment_history(self) -> int:
        return 0

def get_plan(customer: Customer) -> str:
    return customer.billing_plan  # No null check needed

def get_history(customer: Customer) -> int:
    return customer.payment_history  # No null check needed
```

### Simplifying Method Calls

#### Rename Method
**Problem**: Method name doesn't clearly describe what it does.

```python
# Before
def inv_hdlr(self) -> None:
    # Handle inventory

# After  
def handle_inventory(self) -> None:
    # Handle inventory
```

#### Add Parameter
**Problem**: Method needs more information from caller.

```python
# Before
class Account:
    def withdraw(self, amount: float) -> None:
        # Always uses default fee calculation

# After
class Account:  
    def withdraw(self, amount: float, fee_calculator: 'FeeCalculator') -> None:
        # Can use different fee calculations
```

#### Remove Parameter
**Problem**: Parameter is no longer needed.

```python
# Before
def contact_info(self, telephone: str, email: str) -> str:
    # telephone parameter never used
    return f"Email: {email}"

# After
def contact_info(self, email: str) -> str:
    return f"Email: {email}"
```

#### Separate Query from Modifier
**Problem**: Method both returns value and changes object state.

```python
# Before
def found_miscreant(self, people: list[str]) -> str:
    for person in people:
        if person in ("Don", "John"):
            self._send_alert()  # Side effect
            return person
    return ""

# After - Separate query and command
def found_person(self, people: list[str]) -> str:
    """Query - returns value without side effects."""
    for person in people:
        if person in ("Don", "John"):
            return person
    return ""

def check_security(self, people: list[str]) -> None:
    """Command - performs side effects without returning value."""  
    person = self.found_person(people)
    if person:
        self._send_alert()
```

#### Parameterize Method
**Problem**: Multiple methods doing similar things with different values.

```python
# Before
def five_percent_raise(self) -> None:
    self.salary *= 1.05

def ten_percent_raise(self) -> None:
    self.salary *= 1.10

# After
def raise_salary(self, percentage: float) -> None:
    self.salary *= (1 + percentage / 100)
```

#### Introduce Parameter Object
**Problem**: Group of parameters that naturally belong together.

```python
# Before
def amount_invoice_for(start_date: datetime, end_date: datetime, 
                      customer_id: str, product_id: str) -> float:
    pass

# After
@dataclass(frozen=True)
class InvoiceQuery:
    start_date: datetime
    end_date: datetime
    customer_id: str  
    product_id: str

def amount_invoice_for(query: InvoiceQuery) -> float:
    pass
```

#### Replace Parameter with Method Call
**Problem**: Object can get parameter value itself.

```python
# Before
def get_price(self, primary_base_price: float, secondary_base_price: float, 
              tertiary_base_price: float) -> float:
    pass

base_price = self.get_base_price()
secondary_price = self.get_secondary_price()  
tertiary_price = self.get_tertiary_price()
price = self.get_price(base_price, secondary_price, tertiary_price)

# After
def get_price(self) -> float:
    primary_base_price = self.get_base_price()
    secondary_base_price = self.get_secondary_price()
    tertiary_base_price = self.get_tertiary_price()
    # Calculate price...

price = self.get_price()  # Much simpler call
```

#### Replace Constructor with Factory Method
**Problem**: Complex constructor logic or need different creation methods.

```python
# Before
class Employee:
    def __init__(self, type_code: int, name: str, monthly_salary: float = 0, 
                 commission: float = 0, bonus: float = 0) -> None:
        self.name = name
        self.type_code = type_code
        self.monthly_salary = monthly_salary
        self.commission = commission  
        self.bonus = bonus

# Usage is confusing
engineer = Employee(0, "John", 5000)
salesman = Employee(1, "Bob", 0, 1000)
manager = Employee(2, "Alice", 8000, 0, 2000)

# After
class Employee:
    def __init__(self, name: str, type_code: int, monthly_salary: float = 0,
                 commission: float = 0, bonus: float = 0) -> None:
        self.name = name
        self.type_code = type_code
        self.monthly_salary = monthly_salary
        self.commission = commission
        self.bonus = bonus

    @classmethod
    def create_engineer(cls, name: str, salary: float) -> 'Employee':
        return cls(name, 0, salary)

    @classmethod  
    def create_salesman(cls, name: str, commission: float) -> 'Employee':
        return cls(name, 1, 0, commission)

    @classmethod
    def create_manager(cls, name: str, salary: float, bonus: float) -> 'Employee':
        return cls(name, 2, salary, 0, bonus)

# Usage is much clearer
engineer = Employee.create_engineer("John", 5000)
salesman = Employee.create_salesman("Bob", 1000)  
manager = Employee.create_manager("Alice", 8000, 2000)
```

### Dealing with Generalization

#### Pull Up Field/Method
**Problem**: Subclasses have same field/method.

```python
# Before  
class Engineer:
    def __init__(self, name: str) -> None:
        self.name = name  # Duplicate field

class Salesman:  
    def __init__(self, name: str) -> None:
        self.name = name  # Duplicate field

# After
class Employee:
    def __init__(self, name: str) -> None:
        self.name = name

class Engineer(Employee):
    pass

class Salesman(Employee):
    pass
```

#### Push Down Method/Field
**Problem**: Behavior is only relevant to some subclasses.

```python
# Before
class Employee:
    def __init__(self, quota: int) -> None:
        self.quota = quota  # Only relevant for salesmen

class Engineer(Employee):
    pass  # Doesn't need quota

class Salesman(Employee):  
    pass

# After
class Employee:
    pass

class Engineer(Employee):
    pass

class Salesman(Employee):
    def __init__(self, quota: int) -> None:
        self.quota = quota
```

#### Extract Superclass
**Problem**: Two classes have similar features.

```python
# Before - Similar classes
@dataclass
class Department:
    name: str
    staff: list['Employee']
    
    def total_annual_cost(self) -> float:
        return sum(emp.annual_cost() for emp in self.staff)

@dataclass  
class Employee:
    name: str
    id: str
    annual_cost: float

# After - Extract common superclass
@dataclass
class Party:  # Common superclass
    name: str
    
    def annual_cost(self) -> float:
        raise NotImplementedError

@dataclass
class Department(Party):
    staff: list['Employee']
    
    def annual_cost(self) -> float:
        return sum(emp.annual_cost() for emp in self.staff)

@dataclass
class Employee(Party):
    id: str
    _annual_cost: float
    
    def annual_cost(self) -> float:
        return self._annual_cost
```

#### Form Template Method
**Problem**: Subclasses have similar method structure but different details.

```python
# Before - Similar algorithm structure
class Article:
    def print_article(self) -> str:
        result = f"Title: {self.title}\n"
        result += f"Author: {self.author}\n" 
        result += f"Content: {self.content}\n"
        return result

class BlogPost:
    def print_post(self) -> str:
        result = f"Title: {self.title}\n"
        result += f"Author: {self.author}\n"
        result += f"Tags: {', '.join(self.tags)}\n"  # Different detail
        result += f"Content: {self.content}\n"
        return result

# After - Template method pattern
from abc import ABC, abstractmethod

class Publication(ABC):
    def print_publication(self) -> str:  # Template method
        result = f"Title: {self.title}\n"
        result += f"Author: {self.author}\n"
        result += self._print_specific_info()  # Vary this part
        result += f"Content: {self.content}\n"
        return result
    
    @abstractmethod
    def _print_specific_info(self) -> str:
        pass

class Article(Publication):
    def _print_specific_info(self) -> str:
        return ""  # No additional info

class BlogPost(Publication):  
    def _print_specific_info(self) -> str:
        return f"Tags: {', '.join(self.tags)}\n"
```

This refactoring guide combines classic patterns with modern Python 3.12+ features like improved type hints, dataclasses, enums, and pattern matching to create cleaner, more maintainable code.

