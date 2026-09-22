// Liquid Orb — WebGPU 液金球（音频响应）
// 着色器在 orb-shader.wgsl，运行时加载；状态种子与音频规则取自原始实现。
// 对外接口：window.liquidOrb.{getState,setState,setAudioBands}

const stateSeeds = {"idle":[1,1,0,0.44999998807907104,0.7200000286102295,0.28200000524520874,1.4559999704360962,0.1728000044822693,2,0.10000000149011612,0.30000001192092896,0.25999999046325684,0.20000000298023224,0.20000000298023224,0.7616000175476074,13,0.004999999888241291,0,0,1,0.3799999952316284,0,2,0.41999998688697815,0.7699999809265137,0.23000000417232513,65,0,0,1,0.2199999988079071,0.25,0.7200000286102295,5,0.41999998688697815,1.25,0.550000011920929,0.30000001192092896,1.2000000476837158,0.699999988079071,0.7882353067398071,0.7647058963775635,0.7372549176216125,1,0.4313725531101227,0.6196078658103943,0.5686274766921997,1,0.6313725709915161,0.45490196347236633,0.5882353186607361,1,0.40784314274787903,0.3764705955982208,0.5568627715110779,1,0.8823529481887817,0.8627451062202454,0.8352941274642944,1,1,1,1,1,0.8039215803146362,0.8980392217636108,1,1,0.8509804010391235,0.7843137383460999,1,1,0.9176470637321472,0.95686274766922,1,1,0.8627451062202454,0.9176470637321472,1,1,0.027450980618596077,0.0313725508749485,0.05098039284348488,1,0.5098039507865906,0.4745098054409027,0.6078431606292725,1,0.9686274528503418,0.9843137264251709,1,1,0.9372549057006836,0.9647058844566345,0.9921568632125854,1,0.8784313797950745,0.9333333373069763,0.9764705896377563,1,0.8313725590705872,0.9019607901573181,0.9686274528503418,1,0.7333333492279053,0.8352941274642944,0.9529411792755127,1,0.6509804129600525,0.7803921699523926,0.9411764740943909,1,0.529411792755127,0.6901960968971252,0.9215686321258545,1,0.43529412150382996,0.6196078658103943,0.9098039269447327,1,0.43529412150382996,0.6196078658103943,0.9098039269447327,1,0.43529412150382996,0.6196078658103943,0.9098039269447327,1,0.43529412150382996,0.6196078658103943,0.9098039269447327,1,0.43529412150382996,0.6196078658103943,0.9098039269447327,1],"thinking":[1,1,0,1.5,0.7200000286102295,0.30000001192092896,2.799999952316284,0.36000001430511475,2,0.10000000149011612,0.30000001192092896,0.25999999046325684,0.20000000298023224,0.20000000298023224,1.1200000047683716,13,0.004999999888241291,0,0,1,0.3799999952316284,0,2,0.41999998688697815,0.7699999809265137,0.23000000417232513,65,0,0,1,0.2199999988079071,0.25,0.7200000286102295,5,0.41999998688697815,1.25,0.550000011920929,0.30000001192092896,1.2000000476837158,0.699999988079071,1,0.9647058844566345,0.9098039269447327,1,0.4313725531101227,0.9490196108818054,0.8117647171020508,1,1,0.5686274766921997,0.8470588326454163,1,0.4588235318660736,0.41960784792900085,1,1,1,1,1,1,1,1,1,1,0.8039215803146362,0.8980392217636108,1,1,0.8509804010391235,0.7843137383460999,1,1,0.9176470637321472,0.95686274766922,1,1,0.8627451062202454,0.9176470637321472,1,1,0.027450980618596077,0.0313725508749485,0.05098039284348488,1,0.6196078658103943,0.5490196347236633,1,1,0.9686274528503418,0.9843137264251709,1,1,0.9372549057006836,0.9647058844566345,0.9921568632125854,1,0.8784313797950745,0.9333333373069763,0.9764705896377563,1,0.8313725590705872,0.9019607901573181,0.9686274528503418,1,0.7333333492279053,0.8352941274642944,0.9529411792755127,1,0.6509804129600525,0.7803921699523926,0.9411764740943909,1,0.529411792755127,0.6901960968971252,0.9215686321258545,1,0.43529412150382996,0.6196078658103943,0.9098039269447327,1,0.43529412150382996,0.6196078658103943,0.9098039269447327,1,0.43529412150382996,0.6196078658103943,0.9098039269447327,1,0.43529412150382996,0.6196078658103943,0.9098039269447327,1,0.43529412150382996,0.6196078658103943,0.9098039269447327,1]}
const audioRules = [[3,"all",0,1.35,9],[6,"mid",1.5,0,9],[21,"low",0.14,0,1.6],[10,"high",0.30,0,3],[14,"all",0,0.24,6]]
const audioFlowStrengths = {"9":0.8,"10":0.65,"11":0.65,"13":1.0,"14":0.75,"19":1,"21":0.7}

const ribbonStyleIndex = 24;
const ribbonInstanceCount = 221184;
const activationDurationMs = 220;
const settleDurationMs = 650;

let device = null;
let ribbonTarget = null;
let stopped = false;
let state = "idle";
let transitionTargetState = state;
let fromUniforms = new Float32Array(stateSeeds[state]);
let targetUniforms = new Float32Array(stateSeeds[state]);
const displayedUniforms = new Float32Array(stateSeeds[state]);
let transitionStartedAt = 0;
let activeTransitionDuration = 0;
let lastFrameAt = null;
let motionPhase = 0;
let animationFrame = 0;

function applyAudioUniforms(values, bands) {
  const strength = audioFlowStrengths[Math.round(values[15])] ?? 0;
  if (!strength) return;
  for (const [index, band, additive, proportional, ceiling] of audioRules) {
    const input = bands[band];
    const level = (Number.isFinite(input) ? Math.max(0, Math.min(1, input)) : 0) * strength;
    if (!level) continue;
    values[index] = Math.min(
      Math.max(ceiling, values[index]),
      values[index] * (1 + proportional * level) + additive * level,
    );
  }
}

let audioBands = { low: 0, mid: 0, high: 0, all: 0 };

// 传入归一化到 0..1 的频段能量；停止时传全 0
export function setAudioBands(bands = {}) {
  audioBands = Object.fromEntries(
    ["low", "mid", "high", "all"].map((key) => [
      key,
      Number.isFinite(bands[key]) ? Math.max(0, Math.min(1, bands[key])) : 0,
    ]),
  );
}

function srgbToLinear(value) {
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}
function linearToSrgb(value) {
  return value <= 0.0031308 ? value * 12.92 : 1.055 * value ** (1 / 2.4) - 0.055;
}
function mixSrgb(from, to, progress) {
  return linearToSrgb(
    srgbToLinear(from) + (srgbToLinear(to) - srgbToLinear(from)) * progress,
  );
}

function transitionProgress(now) {
  if (activeTransitionDuration === 0) return 1;
  const raw = Math.min(1, Math.max(0, (now - transitionStartedAt) / activeTransitionDuration));
  return transitionTargetState === "active"
    ? 1 - (1 - raw) ** 3
    : raw * raw * (3 - 2 * raw);
}

function sampleTransition(now) {
  const progress = transitionProgress(now);
  for (let index = 3; index < displayedUniforms.length; index += 1) {
    const colorComponent = index >= 40 && (index - 40) % 4 < 3;
    displayedUniforms[index] = colorComponent
      ? mixSrgb(fromUniforms[index], targetUniforms[index], progress)
      : fromUniforms[index] + (targetUniforms[index] - fromUniforms[index]) * progress;
  }
  return displayedUniforms;
}

// 状态名对外只有两个：idle（待机）/ active（在听或在说）
// 内部映射到种子表的 idle / thinking
const STATE_ALIAS = { idle: "idle", active: "thinking", thinking: "thinking" };

export function setState(nextState) {
  const seedKey = STATE_ALIAS[nextState];
  if (!seedKey || !Object.prototype.hasOwnProperty.call(stateSeeds, seedKey)) {
    throw new TypeError(`Unknown liquid orb state: ${nextState}`);
  }
  if (seedKey === state) return;

  const now = performance.now();
  sampleTransition(now);
  fromUniforms = new Float32Array(displayedUniforms);
  targetUniforms = new Float32Array(stateSeeds[seedKey]);
  transitionTargetState = seedKey;
  transitionStartedAt = now;
  activeTransitionDuration = seedKey === "thinking" ? activationDurationMs : settleDurationMs;
  state = seedKey;
}

export function getState() {
  return state === "thinking" ? "active" : "idle";
}

function stopWithError(error) {
  if (stopped) return;
  stopped = true;
  cancelAnimationFrame(animationFrame);
  ribbonTarget?.destroy();
  device?.destroy();
  console.error("[orb]", error);
}

export async function initOrb(canvas, shaderUrl = "orb-shader.wgsl") {
  if (!canvas) throw new Error("orb canvas 不存在");
  if (!navigator.gpu) throw new Error("当前浏览器不支持 WebGPU");

  const adapter = await navigator.gpu.requestAdapter();
  if (!adapter) throw new Error("找不到可用的 WebGPU 适配器");
  device = await adapter.requestDevice();

  const context = canvas.getContext("webgpu");
  if (!context) throw new Error("无法创建 WebGPU 画布上下文");

  const res = await fetch(shaderUrl);
  if (!res.ok) throw new Error(`着色器加载失败: HTTP ${res.status}`);
  const shaderSource = await res.text();

  const format = navigator.gpu.getPreferredCanvasFormat();
  context.configure({ device, format, alphaMode: "premultiplied" });

  const shader = device.createShaderModule({ code: shaderSource });
  const compilation = await shader.getCompilationInfo();
  const errors = compilation.messages.filter((m) => m.type === "error");
  if (errors.length) {
    throw new Error(
      errors.map((m) => `${m.lineNum}:${m.linePos} ${m.message}`).join("\n"),
    );
  }

  const blendPremultiplied = {
    color: { srcFactor: "one", dstFactor: "one-minus-src-alpha", operation: "add" },
    alpha: { srcFactor: "one", dstFactor: "one-minus-src-alpha", operation: "add" },
  };

  const pipeline = device.createRenderPipeline({
    layout: "auto",
    vertex: { module: shader, entryPoint: "vs_main" },
    fragment: {
      module: shader,
      entryPoint: "fs_main",
      targets: [{ format, blend: blendPremultiplied }],
    },
    primitive: { topology: "triangle-list" },
  });

  const ribbonPipeline = device.createRenderPipeline({
    layout: "auto",
    vertex: { module: shader, entryPoint: "ribbon_vs_main" },
    fragment: {
      module: shader,
      entryPoint: "ribbon_fs_main",
      targets: [{
        format,
        blend: {
          color: { srcFactor: "one", dstFactor: "one", operation: "add" },
          alpha: { srcFactor: "one", dstFactor: "one-minus-src-alpha", operation: "add" },
        },
      }],
    },
    primitive: { topology: "triangle-list" },
  });

  const ribbonCompositePipeline = device.createRenderPipeline({
    layout: "auto",
    vertex: { module: shader, entryPoint: "vs_main" },
    fragment: {
      module: shader,
      entryPoint: "ribbon_composite_fs_main",
      targets: [{ format, blend: blendPremultiplied }],
    },
    primitive: { topology: "triangle-list" },
  });

  const values = new Float32Array(displayedUniforms);
  const uniformBuffer = device.createBuffer({
    size: values.byteLength,
    usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
  });
  const bindGroup = device.createBindGroup({
    layout: pipeline.getBindGroupLayout(0),
    entries: [{ binding: 0, resource: { buffer: uniformBuffer } }],
  });
  const ribbonBindGroup = device.createBindGroup({
    layout: ribbonPipeline.getBindGroupLayout(0),
    entries: [{ binding: 0, resource: { buffer: uniformBuffer } }],
  });
  const ribbonSampler = device.createSampler({
    addressModeU: "clamp-to-edge",
    addressModeV: "clamp-to-edge",
    magFilter: "linear",
    minFilter: "linear",
  });
  let ribbonCompositeBindGroup = null;

  device.lost.then((info) => {
    stopWithError(new Error(`WebGPU 设备丢失: ${info.message || info.reason}`));
  });
  device.addEventListener("uncapturederror", (event) => {
    event.preventDefault();
    stopWithError(new Error(`WebGPU 渲染错误: ${event.error.message}`));
  });

  function frame(now) {
    if (stopped) return;
    try {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.floor(canvas.clientWidth * dpr));
      const height = Math.max(1, Math.floor(canvas.clientHeight * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
        ribbonTarget?.destroy();
        ribbonTarget = null;
        ribbonCompositeBindGroup = null;
      }

      values.set(sampleTransition(now));
      const frameDelta = lastFrameAt === null
        ? 0
        : Math.min(0.1, Math.max(0, (now - lastFrameAt) / 1000));
      lastFrameAt = now;
      applyAudioUniforms(values, audioBands);
      motionPhase += frameDelta * Math.max(values[3], 0);
      values[0] = width;
      values[1] = height;
      values[2] = motionPhase / Math.max(values[3], 0.001);
      device.queue.writeBuffer(uniformBuffer, 0, values);

      const isParticleRibbon = Math.round(values[15]) === ribbonStyleIndex;
      const encoder = device.createCommandEncoder();

      if (isParticleRibbon) {
        if (!ribbonTarget || !ribbonCompositeBindGroup) {
          ribbonTarget = device.createTexture({
            size: { width, height },
            format,
            usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.TEXTURE_BINDING,
          });
          ribbonCompositeBindGroup = device.createBindGroup({
            layout: ribbonCompositePipeline.getBindGroupLayout(0),
            entries: [
              { binding: 0, resource: { buffer: uniformBuffer } },
              { binding: 1, resource: ribbonTarget.createView() },
              { binding: 2, resource: ribbonSampler },
            ],
          });
        }
        const particlePass = encoder.beginRenderPass({
          colorAttachments: [{
            view: ribbonTarget.createView(),
            clearValue: { r: 0, g: 0, b: 0, a: 0 },
            loadOp: "clear",
            storeOp: "store",
          }],
        });
        particlePass.setPipeline(ribbonPipeline);
        particlePass.setBindGroup(0, ribbonBindGroup);
        particlePass.draw(6, ribbonInstanceCount);
        particlePass.end();
      }

      const pass = encoder.beginRenderPass({
        colorAttachments: [{
          view: context.getCurrentTexture().createView(),
          clearValue: { r: 0, g: 0, b: 0, a: 0 },
          loadOp: "clear",
          storeOp: "store",
        }],
      });
      if (isParticleRibbon) {
        pass.setPipeline(ribbonCompositePipeline);
        pass.setBindGroup(0, ribbonCompositeBindGroup);
      } else {
        pass.setPipeline(pipeline);
        pass.setBindGroup(0, bindGroup);
      }
      pass.draw(3);
      pass.end();
      device.queue.submit([encoder.finish()]);
      animationFrame = requestAnimationFrame(frame);
    } catch (error) {
      stopWithError(error);
    }
  }

  animationFrame = requestAnimationFrame(frame);

  window.addEventListener("pagehide", () => {
    stopped = true;
    cancelAnimationFrame(animationFrame);
    ribbonTarget?.destroy();
    device?.destroy();
  }, { once: true });
}

window.liquidOrb = Object.freeze({ getState, setState, setAudioBands });
