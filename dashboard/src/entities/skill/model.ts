export interface Skill {
  name: string
  description: string
  tags: string[]
  source: string
  usage_count: number
  builtin: boolean
  body?: string
}
