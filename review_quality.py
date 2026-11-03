"""Shared policy for displaying previously generated picture judgments."""
QUALITY_VERSION=2


def safe_analysis(analysis):
    if analysis.get('verification') in ('local_vision','exact_arithmetic_with_image','verified_geometry','image_quality_check') and analysis.get('quality_version')!=QUALITY_VERSION:
        return {**analysis,'verdict':'uncertain','correct_option':None,'needs_reanalysis':True,
                'feedback':'这条旧分析尚未通过新的核验，暂不据此判对错。',
                'explanation':'原回复可能存在结论与解释不一致。你的答案和反思已保留，可以点击“重新核对本题”。',
                'reflection_prompt':'先核实题目依据，再回顾自己的思路。'}
    return analysis
