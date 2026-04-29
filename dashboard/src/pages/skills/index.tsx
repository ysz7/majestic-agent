import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { apiFetch } from '@/shared/api/client'

interface Skill {
  name: string
  description: string
  trigger: string
  enabled: boolean
}

export function SkillsPage() {
  const { data: skills = [] } = useQuery<Skill[]>({
    queryKey: ['skills'],
    queryFn: () => apiFetch('/api/skills'),
  })

  return (
    <div className="space-y-4 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold">Skills</h2>
        <p className="text-sm text-muted-foreground">{skills.length} skills loaded</p>
      </div>
      {skills.length === 0 && (
        <p className="text-sm text-muted-foreground">No skills found. Add YAML files to ~/.majestic-agent/skills/</p>
      )}
      {skills.map((skill) => (
        <Card key={skill.name}>
          <CardHeader className="pb-2 flex-row items-start justify-between">
            <div>
              <CardTitle className="text-sm font-medium">{skill.name}</CardTitle>
              <CardDescription className="text-xs mt-0.5">/{skill.trigger}</CardDescription>
            </div>
            <Badge variant={skill.enabled ? 'default' : 'secondary'}>
              {skill.enabled ? 'active' : 'disabled'}
            </Badge>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{skill.description}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
