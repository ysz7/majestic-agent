import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Save, Brain, User } from 'lucide-react'
import { getMemoryMd, saveMemoryMd } from '@/shared/api/settings'

function MemoryEditor({
  label,
  value,
  onChange,
  onSave,
  saving,
  dirty,
  icon: Icon,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  onSave: () => void
  saving: boolean
  dirty: boolean
  icon: React.ElementType
}) {
  return (
    <div className="flex flex-col h-full space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">{label}</span>
          <span className="text-xs text-muted-foreground">{value.length} chars</span>
        </div>
        <div className="flex items-center gap-2">
          {dirty && <Badge variant="secondary" className="text-xs">Unsaved</Badge>}
          <Button size="sm" onClick={onSave} disabled={!dirty || saving}>
            <Save className="h-3.5 w-3.5 mr-1.5" />
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </div>
      <Textarea
        className="flex-1 min-h-[calc(100vh-16rem)] font-mono text-xs resize-none"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={`# ${label}\n\nWrite markdown here…`}
        spellCheck={false}
      />
    </div>
  )
}

export function MemoryPage() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['memory-md'], queryFn: getMemoryMd })
  const [agentText, setAgentText] = useState('')
  const [userText, setUserText] = useState('')
  const [agentDirty, setAgentDirty] = useState(false)
  const [userDirty, setUserDirty] = useState(false)

  useEffect(() => {
    if (data) {
      setAgentText(data.agent ?? '')
      setUserText(data.user ?? '')
      setAgentDirty(false)
      setUserDirty(false)
    }
  }, [data])

  const saveAgent = useMutation({
    mutationFn: () => saveMemoryMd({ agent: agentText }),
    onSuccess: () => { setAgentDirty(false); qc.invalidateQueries({ queryKey: ['memory-md'] }) },
  })

  const saveUser = useMutation({
    mutationFn: () => saveMemoryMd({ user: userText }),
    onSuccess: () => { setUserDirty(false); qc.invalidateQueries({ queryKey: ['memory-md'] }) },
  })

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] -m-4 p-4">
      <div className="mb-3">
        <h2 className="text-lg font-semibold">Memory</h2>
        <p className="text-sm text-muted-foreground">
          Markdown files injected into every agent prompt
        </p>
      </div>
      <Tabs defaultValue="agent" className="flex flex-col flex-1 overflow-hidden">
        <TabsList className="w-fit">
          <TabsTrigger value="agent" className="gap-1.5 text-xs">
            <Brain className="h-3.5 w-3.5" /> Agent Memory
            {agentDirty && <span className="h-1.5 w-1.5 rounded-full bg-orange-400 inline-block" />}
          </TabsTrigger>
          <TabsTrigger value="user" className="gap-1.5 text-xs">
            <User className="h-3.5 w-3.5" /> User Profile
            {userDirty && <span className="h-1.5 w-1.5 rounded-full bg-orange-400 inline-block" />}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="agent" className="flex-1 mt-3 overflow-hidden">
          <MemoryEditor
            label="Agent Memory"
            value={agentText}
            onChange={(v) => { setAgentText(v); setAgentDirty(true) }}
            onSave={() => saveAgent.mutate()}
            saving={saveAgent.isPending}
            dirty={agentDirty}
            icon={Brain}
          />
        </TabsContent>
        <TabsContent value="user" className="flex-1 mt-3 overflow-hidden">
          <MemoryEditor
            label="User Profile"
            value={userText}
            onChange={(v) => { setUserText(v); setUserDirty(true) }}
            onSave={() => saveUser.mutate()}
            saving={saveUser.isPending}
            dirty={userDirty}
            icon={User}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
