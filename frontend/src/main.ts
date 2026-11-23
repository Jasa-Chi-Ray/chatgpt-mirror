import { createApp, defineComponent, h } from 'vue'
import { createPinia } from 'pinia'
import TDesign from 'tdesign-vue-next'
import {
  AddIcon, ChevronDownIcon, CodeIcon, DashboardIcon, FileIcon, InternetIcon, NotificationIcon,
  RootListIcon, SearchIcon, SecuredIcon, ServerIcon, UserAddIcon, UserCircleIcon, UserIcon,
} from 'tdesign-icons-vue-next'
import 'tdesign-vue-next/es/style/index.css'

import App from './App.vue'
import router from './router'

const icons = {
  add: AddIcon,
  'chevron-down': ChevronDownIcon,
  code: CodeIcon,
  dashboard: DashboardIcon,
  file: FileIcon,
  internet: InternetIcon,
  notification: NotificationIcon,
  'root-list': RootListIcon,
  search: SearchIcon,
  secured: SecuredIcon,
  server: ServerIcon,
  'user-add': UserAddIcon,
  'user-circle': UserCircleIcon,
  user: UserIcon,
}

const app = createApp(App)
app.component('t-icon', defineComponent({
  props: { name: { type: String, required: true } },
  setup(props) {
    return () => {
      const Icon = icons[props.name as keyof typeof icons]
      return Icon ? h(Icon) : null
    }
  },
}))

app.use(createPinia())
app.use(router)
app.use(TDesign)

app.mount('#app')
