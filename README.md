# AI Agent-Bug Detection and Repair-System
BIT软件体系结构与设计模式课程项目

基于AI Agent的软件项目缺陷自主检测与修复系统

一、项目介绍

1.项目内容

需要完成项目概况与缺陷梳理，包括对自有项目和Github开源项目的功能、技术栈以及存在的典型缺陷进行详细的梳理和分析。还要对开源项目的架构、设计模型及历史bugs进行分析，了解项目的整体结构和缺陷产生的原因。此外，要进行AI Agent架构设计、实现与功能开发，构建能够进行缺陷检测与修复的AI Agent系统。最后，对系统效果进行评估，并探索改进方向。

2.实验对象

本项目以“自有非平凡项目 + Github开源项目”作为实验对象，自有非平凡项目具有一定的复杂性和代表性，而Github开源项目则具有丰富的历史数据和广泛的社区支持。小组选择了小学期项目“智慧医疗管理系统”和github项目requests-cache作为研究对象。

二、项目设计

1.项目架构方案

本项目采用多Agent协作架构，具体包括感知Agent、决策Agent和执行Agent。
感知Agent负责读取项目信息，调用分析工具，提取缺陷特征，并输出结构化数据。决策Agent接收感知Agent输出的数据，判断缺陷的优先级，匹配处理策略，并下达执行指令。执行Agent接收决策Agent的指令，生成修复代码，进行替换测试，并反馈结果。

<img width="1130" height="3276" alt="原型架构转化理解示意" src="https://github.com/user-attachments/assets/fc88d52a-0879-47ef-9349-9cee82c23d1e" />

2.工作流设计

<img width="3556" height="6720" alt="第一次迭代完整工作流" src="https://github.com/user-attachments/assets/6950da75-3449-4788-8603-8257e2cccf63" />
