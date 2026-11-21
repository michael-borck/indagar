import pytest

from indagar.research.planner import plan_question


def test_plan_has_the_question_plus_facets():
    plan = plan_question("  Does X improve Y?  ", max_sub_questions=3)

    assert plan.question == "Does X improve Y?"
    assert len(plan.sub_questions) == 3
    assert plan.sub_questions[0].question == "Does X improve Y?"
    assert all(item.rationale for item in plan.sub_questions)


def test_plan_can_be_a_single_question():
    plan = plan_question("What is X?", max_sub_questions=1)
    assert len(plan.sub_questions) == 1


def test_empty_question_is_rejected():
    with pytest.raises(ValueError):
        plan_question("   ")
