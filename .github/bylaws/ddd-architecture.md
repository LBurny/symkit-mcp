# 子法：DDD 架构规范

> 父法：CONSTITUTION.md 第一章

## 第 1 条：目录结构

```
src/
├── Domain/                    # 领域层（内核）
│   ├── Entities/              # 实体
│   ├── ValueObjects/          # 值对象
│   ├── Aggregates/            # 聚合根
│   ├── DomainServices/        # 领域服务
│   ├── DomainEvents/          # 领域事件
│   └── Repositories/          # Repository 接口（仅接口）
│
├── Application/               # 应用层
│   ├── UseCases/              # 用例
│   ├── DTOs/                  # 数据传输对象
│   ├── Services/              # 应用服务
│   └── Interfaces/            # 外部服务接口
│
├── Infrastructure/            # 基础设施层
│   ├── Persistence/           # DAL 数据访问
│   │   ├── Repositories/      # Repository 实作
│   │   ├── DbContext/         # 数据库上下文
│   │   └── Migrations/        # 数据迁移
│   ├── ExternalServices/      # 外部服务实作
│   └── Messaging/             # 消息队列
│
└── Presentation/              # 呈现层
    ├── API/                   # REST API
    ├── GraphQL/               # GraphQL（可选）
    └── CLI/                   # 命令行接口
```

## 第 2 条：依赖方向

```
Presentation → Application → Domain
                    ↓
              Infrastructure
```

- Domain 不依赖任何外层
- Infrastructure 实作 Domain 定义的接口

## 第 3 条：DAL 规范

### 3.1 Repository 接口（在 Domain 层）
```python
# Domain/Repositories/IUserRepository.py
class IUserRepository(ABC):
    @abstractmethod
    def get_by_id(self, id: UserId) -> Optional[User]: ...
    
    @abstractmethod
    def save(self, user: User) -> None: ...
```

### 3.2 Repository 实作（在 Infrastructure 层）
```python
# Infrastructure/Persistence/Repositories/UserRepository.py
class UserRepository(IUserRepository):
    def __init__(self, db_context: DbContext):
        self._db = db_context
    
    def get_by_id(self, id: UserId) -> Optional[User]:
        # 实际数据库操作
        ...
```

## 第 4 条：命名惯例

| 类型 | 命名规则 | 范例 |
|------|----------|------|
| Entity | 名词单数 | `User`, `Order` |
| Value Object | 描述性名词 | `EmailAddress`, `Money` |
| Repository | `I{Entity}Repository` | `IUserRepository` |
| Use Case | 动词 + 名词 | `CreateOrder`, `GetUserById` |
| Domain Event | 过去式 | `OrderCreated`, `UserRegistered` |

---

## 第 5 条：模块化规范

> 依据宪法第 7.3 条「主动重构原则」订定

### 5.1 文件长度限制

| 类型 | 建议上限 | 硬性上限 | 超过时动作 |
|------|----------|----------|------------|
| 单一文件 | 200 行 | 400 行 | 必须拆分 |
| 类别 (Class) | 150 行 | 300 行 | 提取子类别或组合 |
| 函数 (Function) | 30 行 | 50 行 | 提取私有方法 |
| 模块 (目录) | 10 文件 | 15 文件 | 创建子模块 |

### 5.2 复杂度指针

```python
# 圈复杂度 (Cyclomatic Complexity)
# 建议 ≤ 10，硬性上限 15

# ❌ 过于复杂
def process_order(order):
    if order.status == "pending":
        if order.payment:
            if order.payment.verified:
                if order.items:
                    for item in order.items:
                        if item.in_stock:
                            # ... 更多嵌套
                            
# ✅ 重构后
def process_order(order):
    validate_order_status(order)
    verify_payment(order.payment)
    process_items(order.items)
```

### 5.3 模块拆分策略

当 Domain 模块过大时，按 **子领域** 拆分：

```
# Before: 单一 Domain
src/Domain/
├── Entities/
│   ├── User.py
│   ├── Order.py
│   ├── Product.py
│   ├── Payment.py
│   └── Shipping.py  # 太多了！

# After: 按子领域拆分
src/Domain/
├── Identity/           # 身份子领域
│   ├── Entities/
│   │   └── User.py
│   └── ValueObjects/
│       └── Email.py
│
├── Ordering/           # 订单子领域
│   ├── Entities/
│   │   └── Order.py
│   ├── ValueObjects/
│   │   └── OrderStatus.py
│   └── DomainServices/
│       └── OrderPricing.py
│
├── Catalog/            # 商品目录子领域
│   └── Entities/
│       └── Product.py
│
└── Shipping/           # 物流子领域
    └── Entities/
        └── Shipment.py
```

### 5.4 Application 层拆分

按 **功能群组** 或 **用例** 拆分：

```
src/Application/
├── Identity/           # 对应 Domain/Identity
│   ├── Commands/
│   │   ├── RegisterUser.py
│   │   └── ChangePassword.py
│   └── Queries/
│       └── GetUserProfile.py
│
├── Ordering/           # 对应 Domain/Ordering
│   ├── Commands/
│   │   ├── CreateOrder.py
│   │   └── CancelOrder.py
│   └── Queries/
│       └── GetOrderHistory.py
```

### 5.5 重构触发条件

AI 应在以下情况 **主动建议** 重构：

| 触发条件 | 建议动作 |
|----------|----------|
| 文件超过 200 行 | 「这个文件有点长，建议拆分成...」 |
| 函数超过 30 行 | 「这个函数可以提取出...」 |
| 圈复杂度 > 10 | 「这段逻辑较复杂，建议...」 |
| 重复代码 | 「发现重复模式，建议抽取为...」 |
| 跨层依赖 | 「这里违反了 DDD 分层，应该...」 |

---

## 第 6 条：重构安全网

### 6.1 重构前必须

1. ✅ 确保有测试覆盖（覆盖率 ≥ 70%）
2. ✅ 运行现有测试确认通过
3. ✅ 记录重构原因到 `decisionLog.md`

### 6.2 重构后必须

1. ✅ 运行全部测试
2. ✅ 检查架构是否仍符合 DDD
3. ✅ 更新相关文档
4. ✅ 更新 ARCHITECTURE.md

### 6.3 重构模式参考

| 问题 | 重构模式 | 说明 |
|------|----------|------|
| 函数过长 | Extract Method | 提取私有方法 |
| 类别过大 | Extract Class | 提取新类别 |
| 重复代码 | Extract Superclass / Trait | 抽取共用逻辑 |
| 过多参数 | Introduce Parameter Object | 创建参数对象 |
| 条件过复杂 | Replace Conditional with Polymorphism | 用多态取代条件 |
| 跨层依赖 | Dependency Injection | 依赖注入 |
