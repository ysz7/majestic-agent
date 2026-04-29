export interface UserTable {
  name: string
  rows: number
  columns: string[]
}

export interface TableRows {
  columns: string[]
  rows: Record<string, string>[]
}
