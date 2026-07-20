<template>
  <div class="access-control-page">
    <t-card title="访问限制" bordered>
      <template #subtitle>
        禁止用户访问指定的哈希路由路径，被拦截后会返回上一页并提示
      </template>
      <div class="section">
        <h4>当前拦截的哈希路径</h4>
        <t-tag
          v-for="(path, index) in hashPaths"
          :key="index"
          closable
          style="margin: 4px"
          theme="danger"
          @close="removePath(index)"
        >
          {{ path }}
        </t-tag>
        <div v-if="hashPaths.length === 0" style="color: #999; padding: 12px 0">
          暂无拦截路径
        </div>
      </div>

      <t-divider />

      <div class="section">
        <h4>添加新的拦截路径</h4>
        <t-space style="margin-top: 12px">
          <t-input
            v-model="newPath"
            placeholder="例如 #settings/Billing"
            style="width: 300px"
            @keyup.enter="addPath"
          />
          <t-button theme="primary" @click="addPath">添加</t-button>
        </t-space>
        <div style="color: #999; font-size: 12px; margin-top: 4px">
          请输入以 # 开头的哈希路径
        </div>
      </div>

      <t-divider />

      <div class="section">
        <h4>预设拦截模板</h4>
        <t-space style="margin-top: 12px; flex-wrap: wrap">
          <t-button
            v-for="preset in presets"
            :key="preset"
            variant="outline"
            size="small"
            :disabled="hashPaths.includes(preset)"
            @click="addPreset(preset)"
          >
            {{ preset }}
          </t-button>
        </t-space>
      </div>

      <t-divider />

      <t-button theme="primary" :loading="saving" @click="save">
        保存配置
      </t-button>
      <span v-if="saved" style="color: green; margin-left: 8px">已保存</span>
    </t-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'

const hashPaths = ref<string[]>([])
const newPath = ref('')
const saving = ref(false)
const saved = ref(false)

const presets = [
  '#settings/Billing',
  '#settings/Notifications',
  '#settings/Connectors',
  '#settings/Security',
  '#settings/ParentalControls',
  '#settings/Account',
  '#pricing',
]

onMounted(async () => {
  const data = await request('/0x/user/access-control')
  if (data) {
    hashPaths.value = data.hash_paths || []
  }
})

function addPath() {
  const p = newPath.value.trim()
  if (!p) return
  if (!p.startsWith('#')) {
    MessagePlugin.warning('路径必须以 # 开头')
    return
  }
  if (hashPaths.value.includes(p)) {
    MessagePlugin.warning('路径已存在')
    return
  }
  hashPaths.value.push(p)
  newPath.value = ''
  saved.value = false
}

function removePath(index: number) {
  hashPaths.value.splice(index, 1)
  saved.value = false
}

function addPreset(p: string) {
  if (!hashPaths.value.includes(p)) {
    hashPaths.value.push(p)
    saved.value = false
  }
}

async function save() {
  saving.value = true
  saved.value = false
  const data = await request('/0x/user/access-control', 'POST', { hash_paths: hashPaths.value })
  if (data) {
    saved.value = true
    MessagePlugin.success('配置已保存')
  } else {
    MessagePlugin.error('保存失败')
  }
  saving.value = false
}
</script>

<style scoped>
.access-control-page {
  padding: 24px;
}
.section {
  padding: 8px 0;
}
.section h4 {
  margin: 0 0 8px 0;
}
</style>
