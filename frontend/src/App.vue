<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background-color: #f5f5f5;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

button,
input,
textarea,
select {
  -webkit-user-select: text;
  user-select: text;
}

@supports ((-webkit-backdrop-filter: blur(0)) or (backdrop-filter: blur(0))) {
  .t-popup,
  .t-dialog {
    -webkit-backdrop-filter: blur(0);
    backdrop-filter: blur(0);
  }
}
</style>
