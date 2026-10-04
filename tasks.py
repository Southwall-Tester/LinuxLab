"""Scene-independent task contracts for the nine Linux exercises.

Narrative belongs to scene bundles. Paths below use the stable logical layout;
the active run's bindings render their student-facing names at the boundary.
"""
import copy
import hashlib
import json

import layout
from knowledge import PHASE_CONCEPTS


COURSE_ID = 'linux-foundations'
CONTRACT_VERSION = 1

# The curriculum, required evidence and semantic asset roles are independent of
# narrative, physical filenames, generated values and assessment protocol fields.
# The current course keeps its nine-task sequence; it is not an arbitrary-task
# generator. Scene authors explain why each existing learning action matters.
CONTRACTS = (
    {
        'id': 'locate',
        'concepts': PHASE_CONCEPTS[1],
        'goal': '通过观察隐藏项目确认当前位置，并在已经存在的工作区内新建存放后续资料的子目录；不需要创建工作区本身。',
        'evidence': [
            '学习者提交的定位信息与入口处的隐藏项目相符。',
            '工作区内存在要求的资料目录，且目录类型和位置正确。',
            '提交检查时的当前目录是指定入口。',
        ],
        'assets': ['entry', 'workspace', 'evidence'],
        'prerequisites': [],
        'story_relation': '先确认工作位置并准备资料空间，后续发现的线索才有明确的归属。',
    },
    {
        'id': 'backup',
        'concepts': PHASE_CONCEPTS[2],
        'goal': '完整复制原始资料，在保留原件的前提下建立结构正确的备份。',
        'evidence': [
            '备份包含原始资料中的普通文件、隐藏项和子目录，内容完整。',
            '备份目录层级正确，没有意外增加外层目录。',
            '原始资料仍在原位置，内容未被修改或删除。',
        ],
        'assets': ['originals', 'workspace', 'metrics'],
        'prerequisites': ['locate'],
        'story_relation': '后续整理和修复可能改变工作资料，先保全原始记录才能追溯和恢复。',
    },
    {
        'id': 'organize',
        'concepts': PHASE_CONCEPTS[3],
        'goal': '移动并重命名一份指定说明资料；另一组指定过期文件按名称规律清理，不按该规律批量移动资料。',
        'evidence': [
            '指定资料以要求的名称出现在目标目录，内容保持，原位置不再保留该项。',
            '符合清理规则的所有普通文件均已删除。',
            '规则之外的文件、名单、缓存和隐藏项目内容保持完整。',
        ],
        'assets': ['inbox', 'evidence', 'roster', 'metrics'],
        'prerequisites': ['backup'],
        'story_relation': '将有效资料与过期资料分开，使后续工作可以使用可靠线索且不误删仍需使用的内容。',
    },
    {
        'id': 'extract',
        'concepts': PHASE_CONCEPTS[4],
        'goal': '理解归档成员路径，将归档中的资料完整恢复到指定位置。',
        'evidence': [
            '从归档清单辨认出的标识与本次归档一致。',
            '目标目录中需要的文件内容完整，符合归档中的原始内容。',
            '恢复后的目录层级正确，没有遗漏或多套一层目录。',
        ],
        'assets': ['supplies', 'workspace', 'service'],
        'prerequisites': ['organize'],
        'story_relation': '所需工作资料以归档形式交接，正确恢复后才能继续配置与启动相关服务。',
    },
    {
        'id': 'interpret-log',
        'concepts': PHASE_CONCEPTS[5],
        'goal': '根据记录类型和时间顺序，从日志中辨认最新有效业务信息。',
        'evidence': [
            '所选择的信息来自规则要求的最新有效业务记录。',
            '过期业务记录和后续状态消息中的取值不被当作当前有效答案。',
            '后续状态消息不会覆盖先前有效业务记录，不可简单取日志最后一行。',
            '用于后续配置的相关取值来自同一条有效记录。',
        ],
        'assets': ['evidence', 'logs'],
        'prerequisites': ['extract'],
        'story_relation': '工作安排会更新，只有依据最新有效记录才能避免沿用过期设置。',
    },
    {
        'id': 'configure',
        'concepts': PHASE_CONCEPTS[6],
        'goal': '编辑并保存配置，使其结构、字段与取值满足本次工作要求。',
        'evidence': [
            '磁盘上保存的配置符合规定的键值结构。',
            '必需字段恰好各出现一次，没有多余字段。',
            '本次工作标识得到保留，运行设置与先前确认的有效信息相符。',
        ],
        'assets': ['service', 'logs'],
        'prerequisites': ['interpret-log'],
        'story_relation': '已确认的信息需要写入实际配置并保存，服务才能据此执行当前工作。',
    },
    {
        'id': 'permissions',
        'concepts': PHASE_CONCEPTS[7],
        'goal': '区分配置与脚本的权限需求，设置最小访问范围并验证脚本执行。',
        'evidence': [
            '启动脚本仅允许所有者读取、写入与执行，配置仅允许所有者读取与写入。',
            '两类文件均不向组用户和其他用户开放，且未设置特殊权限位。',
            '脚本原始内容得到保留，并已成功执行产生本次有效结果记录。',
        ],
        'assets': ['service'],
        'prerequisites': ['configure'],
        'story_relation': '工作服务既要能启动，也要限制配置的访问范围；执行结果为后续交付提供依据。',
    },
    {
        'id': 'process',
        'concepts': PHASE_CONCEPTS[8],
        'goal': '另行启动独立的短时练习程序，从真实进程列表中辨认本局仍然存活的该进程，练习观察进程身份和生命周期。',
        'evidence': [
            '提交的进程编号对应本次练习启动的目标进程。',
            '检查时目标进程仍然存活，过期编号不被接受。',
        ],
        'assets': ['logs'],
        'prerequisites': ['permissions'],
        'story_relation': '为学习运行状态观察，本关另行启动一个短时练习进程，检查时需确认它仍存活。它不是上一关产生结果记录后结束的脚本，不能把它描述为上一关服务一直在运行。',
    },
    {
        'id': 'deliver',
        'concepts': PHASE_CONCEPTS[9],
        'goal': '综合整理、配置、权限和归档操作，生成内容完整且结构准确的交付物。',
        'evidence': [
            '交付归档只包含规定的配置、完整名单和本次有效执行结果，没有草稿或多余文件。',
            '归档成员路径、普通文件类型与配置权限符合要求，不含重复或越界成员。',
            '交付配置依据最新最终业务记录，字段完整、唯一且没有额外字段。',
            '归档中的内容已反映最终修改，先前建立的完整备份仍保留。',
        ],
        'assets': ['finale', 'roster', 'service', 'workspace', 'delivery'],
        'prerequisites': ['process'],
        'story_relation': '接收方需要可直接使用的完整资料；交付前必须核对包内实际内容，而不只检查外部工作文件。',
    },
)


def task_ids():
    return tuple(contract['id'] for contract in CONTRACTS)


def generation_contract():
    """Export the curriculum for generation without session state or answers."""
    return {
        'course_id': COURSE_ID,
        'version': CONTRACT_VERSION,
        'tasks': copy.deepcopy(list(CONTRACTS)),
    }


def contract_hash():
    """Identify the exact curriculum contract independently of JSON formatting."""
    encoded = json.dumps(generation_contract(), ensure_ascii=False,
                         sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def mode(s, final=False, initial=False):
    """Keep older materials stable while new instances use neutral mode values."""
    if initial:
        return 'maintenance'
    if s.get('material_version') == 2:
        return 'deliver' if final else 'active'
    return 'evacuate' if final else 'rescue'


def requirements(n, s):
    """Render a task's technical requirements without adding a story or solution."""
    if not isinstance(n, int) or not 1 <= n <= 9:
        raise ValueError('关卡编号必须是 1 到 9。')
    station = s['station_id']
    cleanup_goal = (
        '清理规则：只删除 inbox 中名称以 decoy- 开头、以 .tmp 结尾的所有普通文件。\n'
        '除下述需要移动的文件外，保留其他文件及其内容，包括名单、识别指南、普通缓存和隐藏缓存。\n'
        '这次练习按名称规律批量选择文件：尝试用 * 表达规则，操作前先查看匹配范围。'
        if s.get('cleanup_version', 0) >= 1 else
        '清理规则：只删除 inbox 中的 decoy-a.tmp 和 decoy-b.tmp，保留 crew.csv。\n'
        '也可以尝试用 * 按共同名称规律选择这两个文件，操作前先查看匹配范围。')
    tasks = [
        '''实验根目录是 station。本关需要完成三件事：
1. 进入 airlock，找出隐藏的 .beacon-XXXX 项目，记下四位数字。
2. 在 station/work 下创建 evidence 目录，作为后续资料的存放处；本关先建好空目录即可。
3. 如果离开了 airlock，必须先回到 station/airlock，再运行 lab check 提交。
第一步可以试试 ls，接下来由你探索。
提交位置：station/airlock（不能在 work 或 evidence 里提交本关）。
提交命令：lab check 四位数字（请把“四位数字”替换成你发现的数字）。
检查会同时确认：数字正确、work/evidence 已建立、你当前位于 airlock。''',
        '''目标：完整复制 station/blackbox 目录为 station/work/backup。
包括隐藏的校验文件和子目录；blackbox 原件不能丢失或被改动。
注意最终层级是 work/backup/boot.log，不是 work/backup/blackbox/boot.log。
提交：lab check。现在不需要再输入四位数字。''',
        f'''{cleanup_goal}
目标：把 station/inbox/route.pending 移动并改名为 station/work/evidence/route.txt；
移动后原位置不应再有 route.pending。
提交：lab check。''',
        '''可用归档：supplies/rescue.tar.gz。
目标：将归档文件完整恢复到 station/work/recovered，保持原始内容，不能多套一层目录。
清单 manifest.txt 记录了归档标识 SEAL，需要你找到它以确认归档身份。
提交：lab check 标识值。''',
        '''目标：按资料中的记录规则确定当前有效的授权码 CODE，并记下配套的频道 CHANNEL，供后续配置使用。
手头资料：station/work/evidence/route.txt 和 station/logs/comms.log。
日志同时包含旧记录和状态消息，需要区分记录类型与有效性。
提交：lab check 当前有效的授权码。''',
        f'''待编辑文件：work/recovered/relay.conf。
目标：配置中的 MODE={mode(s)}，CHANNEL 和 AUTH 分别对应上一关确认的频道与授权码。
STATION={station} 必须保留；配置只包含这四个字段，每个字段各出现一次。
提交：lab check。以保存后的配置为准。''',
        '''目标：work/recovered/relay.sh 仅允许所有者读、写、执行；
同目录的 relay.conf 仅允许所有者读、写。两者都不允许组用户和其他用户访问，也不设置特殊权限位。
执行该脚本，取得它生成的 receipt.txt 文件；保留脚本原始内容。
提交：lab check。只改权限、没有启动成功还不能通过。''',
        '''先运行 lab load，它会启动最多 90 秒、低占用的练习进程 station-pulse。
目标：从系统中辨认出本局正在运行的 station-pulse，确定它的进程编号 PID。
提交：lab check 这个PID。必须是本局仍然存活的练习进程，旧 PID 无效。
若已超时，可以重新 lab load。''',
        f'''这次只给交付要求，由你决定命令顺序。
可用资料：finale/capsule.tar.gz 中的配置草稿、finale/final.log 中的最终记录，
以及 inbox/crew.csv 名单和 work/recovered/receipt.txt 文件。

交付物：work/rescue.tar.gz。包内恰有以下三个普通文件（可包含 dispatch 目录条目）：
  dispatch/relay.conf —— MODE={mode(s, final=True)}，STATION={station}；CHANNEL 和 AUTH
  对应最新 FINAL 指令。仅所有者可读写，其余用户无权限，不设置特殊权限位。
  dispatch/crew.csv —— 本局完整名单。
  dispatch/receipt.txt —— 本局脚本生成的有效文件。
配置只包含上述四个字段，每个字段各出现一次。归档不能夹带草稿或其他文件。
保留 work/backup 备份。提交：lab check。
成功后将生成完成凭证和可分享的 JSON 通关报告。''',
    ]
    return layout.text(s, tasks[n - 1])
