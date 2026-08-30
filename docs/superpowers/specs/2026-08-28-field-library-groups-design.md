# 性能大类与种子字段 · 设计规格

日期：2026-08-28
范围：工作台真实任务补齐的第三块——钢铁模板默认性能大类、公共库种子字段、项目可自建大类、新建私有字段挂入大类。
总目标：1) 字段勾选自动挂阶段（`2026-08-28-field-stage-config-design.md`）2) 文献上传与多篇抽取（`2026-08-28-paper-upload-batch-design.md`）3) 本文件。
前置：挂段与草稿保存以第 1 块为准。本块规定有哪些默认大类、库里有哪些种子、用户如何新增大类。

## 1. 目标与非目标

### 1.1 目标

- 钢铁模板预置一组默认性能大类。细化字段（库种子或项目私有）通过 `group` 挂进去。
- **项目可以自建大类**（名称自定），写入该项目覆盖层，不写回模板或公共库。
- 勾选某大类下的字段后，按第 1 块自动出现对应抽取阶段；未勾选则不多出该步。自建大类同样：有字段挂上才生成阶段。
- 公共库补齐硬度、电导率、冲击韧性三条种子。
- 新建字段：中文名 + 类别；性能必须选一个大类（默认六类或本项目自建类）。`id` 可自动生成。写入私有字段。

### 1.2 非目标

- 把历史 cuti / 耐蚀 / 无磁整份字段迁进公共库
- 把只读快照改成可跑
- 另建与 `electrical_conductivity` 同义的 `conductivity`
- 把自建大类写回 `steel.json` 模板
- 策略文案、pipeline prompt 结构、复核 / 导出
- 重算 `demo_steel` 已保存的 `steps`

## 2. 默认大类（模板）

`configs/templates/steel.json` 的 `property_groups`：

| id | 显示名 | 库种子 |
| --- | --- | --- |
| `mechanical_properties` | 力学性能 | 已有屈服/抗拉/伸长 + `hardness` |
| `magnetic_properties` | 磁性能 | 已有 `permeability` |
| `electrical_properties` | 电性能 | `electrical_conductivity` |
| `impact_properties` | 冲击性能 | `impact_toughness` |
| `corrosion_properties` | 腐蚀性能 | 无种子，供挂入 |
| `phase_stability` | 相稳定性 | 无种子，供挂入 |

blank 模板仍无公共库，新建性能字段的大类下拉 = 上表六类 + 该项目自建类。

挂段时阶段显示名取合并后的大类表（模板 + 项目自建）。`electrical_properties` 对应段 id `electrical`、名「电性能」。

配置页性能勾选按合并后的大类分组。某类下当前没有任何库字段或私有字段则不显示空分组（自建类在「大类管理」里仍可见，见第 3 节）。

## 3. 项目自建大类

覆盖层增加 `property_groups`（数组，可空）。每项：`id`（稳定）、`name`（显示名）。

有效大类 = 模板 `property_groups` + 覆盖层 `property_groups`。覆盖层不得使用已存在的模板 id；重名显示名允许但 id 必须不同。

配置页「添加性能大类」：

- 必填中文名（如「疲劳性能」）。
- `id` 默认：英文蛇形 + `_properties`（无法转写则 `custom_` + 时间戳后 6 位 + `_properties`）。用户可改，须匹配 `[a-z][a-z0-9_]*`，且不与已有大类 id 冲突。
- 只写入草稿中的覆盖层 `property_groups`，与字段/阶段一起在「保存配置」时落盘。不写模板。
- 刚加完、还没有字段时：不生成空抽取阶段（与第 1 块「空段保存时丢掉」一致）。新建字段的大类下拉里立刻能选到它。

删除自建大类（仅覆盖层项，模板六类不可删）：

- 若已有已选性能字段挂在该类：拦住，提示先把字段改挂到别的类或取消勾选。
- 否则从草稿去掉该类。

模板六类不可改 id、不可删；显示名本块不提供项目级改名（改阶段名仍按第 1 块，只影响 `steps[].name`）。

自建大类与「添加性能阶段」不是一回事：大类是字段归属；阶段是抽取步骤。勾选该类下第一个字段时才按第 1 块建段。

## 4. 种子字段

写入 `configs/field_library/steel.json`：

| id | label | category | group | value_type |
| --- | --- | --- | --- | --- |
| `hardness` | 硬度 | property | mechanical_properties | number_with_unit |
| `electrical_conductivity` | 电导率 | property | electrical_properties | number_with_unit |
| `impact_toughness` | 冲击韧性 | property | impact_properties | number_with_unit |

规则要点：硬度/电导/冲击均只抽原文实测，单位跟原文；冲击不要与 KIC/JIC 混淆。不新增 `conductivity`。时效、冷轧等历史钛铜字段不进库。

## 5. 新建私有字段

- 必填：中文名、类别。
- 性能：必选一个有效大类（第 2 节 + 第 3 节），写入 `group`。
- 可选：规则、正反例。
- `id`：默认由中文名生成蛇形；冲突则不能加入。
- 性能默认 `value_type=number_with_unit`，其它默认 `string`。
- 进入草稿已选并按第 1 块挂段；须「保存配置」才落盘。

## 6. 与第 1 块的衔接

第 1 块 3.2 建段时的显示名：先查覆盖层 `property_groups`，再查模板，都没有则用 `group` 本身。

`generate_steps`：按「模板大类顺序，再接覆盖层自建大类顺序」，只为已选且该组有字段的大类生成段。

打开已有项目：已存 `steps` 不按新大类重生成。`demo_steel` 不会自动多出电/冲击段。

## 7. 验收

1. 新钢铁项目只勾「电导率」：阶段为骨架 → 电性能。
2. 再勾「硬度」：力学段含硬度芯片。
3. 添加大类「疲劳性能」，新建「疲劳极限」挂入该类，保存：覆盖层有自建 `property_groups` 项；阶段出现「疲劳性能」；模板与公共库文件无此类、无此字段。
4. 自建大类尚无字段时保存：磁盘 `steps` 无空段；新建字段下拉仍能选到该类。
5. 删除仍有已选字段的自建大类：被拦住。
6. 中文名为空或性能未选大类：不能加入。
7. 打开 `demo_steel`：已存力学段不变。
8. 回归：第 1 块草稿保存、第 2 块上传与多篇抽取不变。

## 8. 测试

- 模板六类 + 库三条种子的 `group`/`label`。
- `generate_steps`：只选电导 → entity + electrical。
- 覆盖层带自建 group 与对应私有字段时，`generate_steps` 含该段。
- 保存后 `property_groups` 只出现在 `configs/projects/<id>.json`，不出现在 `templates/steel.json`。

## 9. 代码要点

- `configs/templates/steel.json`、`configs/field_library/steel.json`：默认大类与种子。
- 覆盖层：`property_groups`。
- `app/`：大类管理 + 新建字段下拉用合并列表；性能勾选按合并大类分组。
- `config_model.generate_steps` / 第 1 块挂段：显示名读合并大类表。
