---
name: Feature Request
about: Suggest a new feature or improvement
title: '[feature]: '
labels: ['enhancement', 'needs-triage']
body:
  - type: markdown
    attributes:
      value: |
        Have a feature idea? Let us know!
  - type: input
    id: title
    attributes:
      label: Feature Title
      description: A concise title for the feature.
      placeholder: "Dark mode support"
    validations:
      required: true
  - type: textarea
    id: description
    attributes:
      label: Description
      description: Explain the feature and why it would be useful.
      placeholder: |
        I would like to be able to...
    validations:
      required: true
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives Considered
      description: Any alternative solutions you've thought of.
      placeholder: "I could use a browser extension, but..."
      render: markdown
    validations:
      required: false
  - type: textarea
    id: implementation
    attributes:
      label: Implementation Ideas
      description: If you have ideas on how to implement this, share them!
      placeholder: "I think this could be done by..."
    validations:
      required: false
  - type: checkboxes
    id: checks
    attributes:
      label: Checklist
      options:
        - label: I have searched for existing feature requests
          required: true
        - label: This is not a duplicate request
          required: true
