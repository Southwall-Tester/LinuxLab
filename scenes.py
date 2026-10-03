"""Narrative presentation is independent of Linux paths and assessment rules."""

SCENES = {
    'space': {'title': '失联空间站', 'description': '科幻探索与空间站救援', 'terms': {}},
    'ocean': {'title': '深海观测站', 'description': '海洋探索与潜航救援',
              'terms': {'失联空间站': '深海观测站', '空间站': '海底站', '气闸': '隔水舱',
                        '黑匣子': '航行记录', '救援舱': '物资舱', '地面站': '岸上中心',
                        '船员': '潜航员', '返航轨道': '返航航线'}},
    'museum': {'title': '数字档案馆', 'description': '档案保护与数字修复',
               'terms': {'失联空间站': '数字档案馆', '空间站': '档案馆', '气闸': '入口终端',
                         '黑匣子': '原始档案', '救援舱': '修复资料包', '地面站': '管理中心',
                         '船员': '档案员', '返航轨道': '安全通道', '救援': '恢复'}},
}


def render(text, state):
    scene = SCENES.get(state.get('scene', 'space'), SCENES['space'])
    for old, new in scene['terms'].items():
        text = text.replace(old, new)
    return text


def choose(state, name=''):
    if not name:
        current = state.get('scene', 'space')
        return '\n'.join(['当前情境：' + SCENES.get(current, SCENES['space'])['title'],
                          *[f'  {key} · {value["title"]} · {value["description"]}' for key, value in SCENES.items()],
                          '用 lab scene 名称 切换；情境名称变化，路径、命令、知识点和检查标准保持一致。'])
    if name not in SCENES:
        raise ValueError('没有这个情境。用 lab scene 查看可选名称。')
    state['scene'] = name
    return '已选择：' + SCENES[name]['title'] + '。输入 lab 查看当前任务。'
