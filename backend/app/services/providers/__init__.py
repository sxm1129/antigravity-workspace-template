"""Video/Image provider implementations.

Each provider module implements the async generation pattern:
  POST create task → poll status → download → save to media_volume
"""
