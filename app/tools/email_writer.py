def outreach_templates(role_titles):
    emails = {}
    for title in role_titles:
        emails[title] = (
            f"Subject: Exploring a {title} role at our startup\n\n"
            f"Hi {{name}},\n\n"
            f"We’re building our v1 product and your background looks relevant. "
            f"Would you be open to a short chat about a {title} opportunity?\n\n"
            f"Best,\nHR"
        )
    return emails
