"""Chinese input guidance shared by lab commands and Bash lookup failures."""
import argparse
import difflib
import shlex

LAB_SCOPE = '使用范围：lab 及其子命令仅由本平台的实验终端提供，不是 Linux 通用命令；换到其他环境不能默认使用。'


def native_help(topic=''):
    """Recommend native documentation without replacing any native command."""
    if topic in ('cd', 'pwd', 'exit', 'help', 'history'):
        return f'help {topic}（Bash 内置帮助）'
    if topic == 'navigation':
        return 'help cd 或 help pwd（Bash 内置帮助）'
    if topic in ('glob', '*'):
        return 'man bash，查阅文件名展开（Pathname Expansion）'
    if topic == 'vim':
        return 'Vim 内用 :help 查编辑操作；终端用 vim --help 或 man vim 查启动用法'
    if topic in ('ls', 'mkdir', 'cp', 'mv', 'rm', 'tar', 'cat', 'tail', 'head',
                 'chmod', 'top', 'grep', 'find', 'du', 'df', 'less', 'man'):
        return f'{topic} --help；man {topic}'
    return '外部命令如 cp --help、man cp；Bash 内置命令如 help cd；Vim 内用 :help'


USAGE = {
    'mission': 'lab（查看当前任务，不需要再加参数）',
    'status': 'lab status（查看进度，不需要再加参数）',
    'help': 'lab help（查看帮助，不需要再加参数）',
    'root': 'lab root（查看站点路径，不需要再加参数）',
    'learn': 'lab learn（查看本关用法，不需要再加参数）；查某个命令请用 lab notes 命令名',
    'notes': 'lab notes（本平台中文笔记目录），或 lab notes 命令名（一次查询一个，如 lab notes tail）；也鼓励查原生命令帮助，如 tail --help、man tail',
    'hint': 'lab hint（逐级提示），或 lab hint 1、lab hint 2、lab hint 3；级别只能是 1、2、3',
    'check': 'lab check，或 lab check 答案（最多一个答案；是否需要答案以本关任务为准）',
    'load': 'lab load（启动本局探针，不需要再加参数）',
    'stop': 'lab stop（停止本局探针，不需要再加参数）',
    'repair': 'lab repair（恢复本关起点，不需要再加参数）',
    'report': 'lab report（查看报告，不需要再加参数）',
    'concepts': 'lab concepts（查看本关知识点）',
    'notebook': 'lab notebook（查看个人学习手册）',
    'review': 'lab review [知识点] [A|B|C]（查看复习清单、题目或提交本题答案）',
    'tutor': 'lab tutor ["你的问题"] [--level 1|2|3] [--topic 知识点] [--offline]（针对当前关求助）',
    'ai': 'lab ai init（创建本地 API 配置），或 lab ai status（只检查配置格式）',
    'tracking': 'lab tracking [on|off|status]（开启、关闭或查看本地操作记录状态）',
    'activity': 'lab activity（查看最近的本地操作记录）',
    'scene': 'lab scene [主题名或JSON文件]；lab scene --generate "兴趣主题" [--output 文件.json]；配套文件命名的新周目用 bash start.sh --new --scene 主题或JSON文件',
    'prepare': '在项目目录运行 bash start.sh；新局用 bash start.sh --new',
    'doctor': '在项目目录运行 bash start.sh --doctor',
    'relay': '在第七关按任务说明运行中继脚本，不需要给 lab relay 加参数',
}
PUBLIC_COMMANDS = [name for name in USAGE if name not in ('prepare', 'doctor', 'relay')]
SHELL_COMMANDS = ['lab', 'ls', 'cd', 'pwd', 'mkdir', 'cp', 'mv', 'rm', 'tar', 'cat',
                  'head', 'tail', 'vim', 'chmod', 'top', 'grep', 'find', 'du', 'df', 'exit']


class InputError(ValueError):
    pass


def closest(word, choices):
    matches = difflib.get_close_matches(word.lower(), choices, n=1, cutoff=0.65)
    return matches[0] if matches else None


def spelling_detail(wrong, right):
    if wrong.lower() == right and wrong != right:
        return '命令名区分大小写。'
    if len(right) == len(wrong) + 1:
        for i, char in enumerate(right):
            if right[:i] + right[i + 1:] == wrong:
                return f'{wrong} 少了一个 {char}，应为 {right}。'
    if len(wrong) == len(right) + 1:
        for i, char in enumerate(wrong):
            if wrong[:i] + wrong[i + 1:] == right:
                return f'{wrong} 多了一个 {char}，应为 {right}。'
    return f'你可能想输入 {right}。'


def unknown_lab_command(command, rest):
    if command == 'exit':
        return '退出实验请直接输入 exit，前面不用加 lab。'
    if command in SHELL_COMMANDS and command != 'lab':
        return (f'{command} 是终端命令，前面不用加 lab。\n'
                '如果要执行它，请重新输入：' + shlex.join([command, *rest]) + '\n'
                '原生用法帮助：' + native_help(command) + '\n'
                f'本平台中文补充笔记：lab notes {command}')
    if command == 'lab':
        return 'lab 重复输入了；只需一个 lab。输入 lab help 查看写法。'
    suggestion = closest(command, PUBLIC_COMMANDS)
    message = f'没有 lab {command} 这个命令。'
    if suggestion:
        message += '\n' + spelling_detail(command, suggestion)
        message += '\n请重新输入：' + shlex.join(['lab', suggestion, *rest])
    else:
        message += '\n输入 lab help 查看可用命令。'
    return message


def runtime_error(error):
    path = str(getattr(error, 'filename', None) or '当前文件或目录')
    if isinstance(error, FileNotFoundError):
        return f'找不到文件或目录：{path}。请核对当前位置、名称和大小写。'
    if isinstance(error, PermissionError):
        return (f'没有权限访问：{path}。请检查文件及所在目录的权限。'
                '原生帮助：chmod --help 或 man chmod；本平台中文笔记：lab notes chmod。')
    if isinstance(error, IsADirectoryError):
        return f'这里需要文件，但路径指向了目录：{path}。请核对文件名和目录层级。'
    if isinstance(error, NotADirectoryError):
        return f'路径中有一部分不是目录：{path}。请检查是否把文件名当成目录。'
    if isinstance(error, UnicodeError):
        return '文件中的文字编码无法读取。请使用 UTF-8 文本保存，并保留原来的字段名称。'
    return str(error)


def unknown_topic(topic, choices):
    suggestion = closest(topic, choices)
    message = f'笔记里没有 {topic} 这个主题。'
    if suggestion:
        message += '\n' + spelling_detail(topic, suggestion)
        message += '\n请重新输入：' + shlex.join(['lab', 'notes', suggestion])
    return message + '\n输入 lab notes 查看笔记目录。'


def shell_lookup_error(command, rest):
    if command == 'cd..':
        return 'cd 和 .. 之间需要空格。\n请重新输入：' + shlex.join(['cd', '..', *rest])
    for name in PUBLIC_COMMANDS:
        if command == 'lab' + name:
            return ('lab 和 ' + name + ' 之间需要空格。\n请重新输入：'
                    + shlex.join(['lab', name, *rest]))
    if command in SHELL_COMMANDS:
        return (f'找不到 {command} 命令；它可能尚未安装，或不在当前命令搜索路径中。\n'
                '请核对环境；在项目目录运行 bash setup.sh --check 可以检查实验依赖。')
    message = f'终端找不到 {command} 这个命令。'
    suggestion = closest(command, SHELL_COMMANDS)
    if suggestion and '/' not in command:
        message += '\n' + spelling_detail(command, suggestion)
        message += '\n请重新输入：' + shlex.join([suggestion, *rest])
    else:
        message += '\n请检查命令拼写、路径和空格；实验帮助可用 lab help。'
    return message


class LabParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('add_help', False)
        kwargs.setdefault('allow_abbrev', False)
        super().__init__(*args, **kwargs)

    def error(self, message):
        command = getattr(self, 'command_name', self.prog.split()[-1])
        usage = USAGE.get(command, 'lab help（查看可用命令）；实验命令以 lab 开头')
        raise InputError('参数写法不对，命令未执行。\n用法：' + usage)
