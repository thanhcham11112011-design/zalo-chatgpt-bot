from services import contact_service


def greeting_router(user_id, question, answer_greeting, clear_user_state):
    answer = answer_greeting(question)

    if answer:
        clear_user_state(user_id)
        return answer

    return None


def contact_router(user_id, question, sheet_api, user_states):
    contact_answer = contact_service.handle_contact_flow(
        user_id=user_id,
        question=question,
        sheet_api=sheet_api,
        user_states=user_states
    )

    if contact_answer:
        return contact_answer

    if contact_service.is_contact_request(question):
        return contact_service.start_contact_flow(
            user_id=user_id,
            user_states=user_states
        )

    return None


def procedure_router(
    user_id,
    question,
    answer_context_question,
    answer_sub_menu_number,
    answer_menu_number,
    answer_menu_keyword
):
    context_answer = answer_context_question(user_id, question)

    if context_answer:
        return context_answer

    sub_menu_answer = answer_sub_menu_number(user_id, question)

    if sub_menu_answer:
        return sub_menu_answer

    menu_number_answer = answer_menu_number(user_id, question)

    if menu_number_answer:
        return menu_number_answer

    menu_keyword_answer = answer_menu_keyword(user_id, question)

    if menu_keyword_answer:
        return menu_keyword_answer

    return None


def search_router(
    user_id,
    question,
    sheet_api,
    build_sheet_answer,
    set_user_state,
    is_broad_question,
    build_search_options
):
    context_items = sheet_api.search(
        question,
        limit=5
    )

    if is_broad_question(question) and len(context_items) > 1:
        return build_search_options(
            user_id,
            context_items
        )

    sheet_answer = build_sheet_answer(
        question,
        context_items
    )

    if sheet_answer:
        if context_items:
            set_user_state(user_id, {
                "level": "procedure_detail",
                "sheet_name": context_items[0].get("_SOURCE_SHEET", ""),
                "procedure": context_items[0]
            })

        return sheet_answer

    return None


def ai_router(
    user_id,
    question,
    context_items,
    get_history_text,
    gemini_service
):
    try:
        history_text = get_history_text(user_id)

        return gemini_service.ask(
            question=question,
            context_items=context_items,
            history_text=history_text
        )

    except Exception as e:
        print("GEMINI FALLBACK ERROR:", e)

        return (
            "Xin lỗi, hiện hệ thống chưa tìm thấy nội dung phù hợp. "
            "Quý công dân vui lòng nhập rõ hơn nội dung cần hỏi hoặc nhập 'menu' "
            "để quay lại danh mục hỗ trợ."
        )
