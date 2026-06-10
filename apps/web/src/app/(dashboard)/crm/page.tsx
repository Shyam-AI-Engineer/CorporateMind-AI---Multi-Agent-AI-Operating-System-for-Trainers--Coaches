"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ActivityTimeline } from "@/features/crm/ui/activity-timeline";
import { FollowUpList } from "@/features/crm/ui/follow-up-list";
import { PipelineBoard } from "@/features/crm/ui/pipeline-board";

export default function CRMPage() {
  return (
    <div className="flex flex-col gap-1 p-6">
      <div className="mb-4">
        <h1 className="text-xl font-semibold">CRM</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Track leads through your pipeline and monitor activity and follow-ups.
        </p>
      </div>

      <Tabs defaultValue="pipeline">
        <TabsList>
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="activities">Activity Timeline</TabsTrigger>
          <TabsTrigger value="followups">Follow-Ups</TabsTrigger>
        </TabsList>

        <TabsContent value="pipeline">
          <PipelineBoard />
        </TabsContent>

        <TabsContent value="activities">
          <ActivityTimeline />
        </TabsContent>

        <TabsContent value="followups">
          <FollowUpList />
        </TabsContent>
      </Tabs>
    </div>
  );
}
