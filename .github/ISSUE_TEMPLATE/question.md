---
name: Question
about: Ask a question about the project
title: '[question]: '
labels: ['question']
body:
  - type: textarea
    id: question
    attributes:
      label: Question
      description: Ask your question here.
      placeholder: "How do I...?"
    validations:
      required: true
  - type: checkboxes
    id: checks
    attributes:
      label: Checklist
      options:
        - label: I have checked the documentation
          required: true
        - label: I have searched existing questions
          required: true
